"""Adapter: old saved compositions (Clip/XFade + Fade/Reverb/ReverbSweep/Delay/FilterSweep)
-> plan v2 (single source), rendered by recut.engine.

Exact (within 1e-6 of `recut.compositor.compose`): plain concatenation and `XFade`, including
the old `qsin` curve (fade-out `1 - sin`, which is not the contract's `equal_power`). The v2
contract has no shape for that, so the adapter also returns `legacy_xfades`, an internal hint
`render_plan(..., _legacy_xfades=...)` uses to reproduce the old overlap length and curves.

Approximate (musically equivalent, not sample-identical):
  Fade            -> `gain` ramp over the clip (vol 0..1 -> dB, "-inf" for 0); `log` -> `log`
  Reverb          -> clip `reverb` device: room_size -> decay (devices.REVERB_DECAY_TABLE),
                     wetness -> dry_wet, damping -> hi_cut; the tail now rings on past the clip
  ReverbSweep     -> the same reverb + a `dry_wet` ramp
  Delay           -> clip `delay` device (unfiltered, no ping-pong)
  FilterSweep     -> clip `auto_filter` + a `frequency` ramp (curve > 1 -> exp, < 1 -> log)
Only the first Fade per clip is kept (a second one is reported in `warnings`).
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from recut import devices as dev_mod
from recut.compositor.effects import Delay, Effect, Fade, FilterSweep, Reverb, ReverbSweep
from recut.compositor.nodes import Clip, XFade
from recut.contracts.plan import ClipNode, Plan
from recut.engine import _clip_bounds, render_plan
from recut.map.parser import beats_to_seconds, parse_recut_map
from recut.primitives.reverb import PRESETS

_SHAPES = {"linear": "linear", "log": "log", "exp": "exp", "qsin": "equal_power"}


@dataclass
class LegacyPlan:
    plan: Plan
    legacy_xfades: dict[str, tuple[float, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _db(v: float):
    return "-inf" if v <= 0 else 20 * float(np.log10(v))


def composition_to_plan(nodes: list, source_name: str, audio_path: Path, map_path: Path) -> LegacyPlan:
    """Convert a legacy node list (all on one source) into a v2 Plan."""
    m = parse_recut_map(map_path)
    clips: list[dict] = []
    legacy: dict[str, tuple[float, str]] = {}
    warnings: list[str] = []
    for i, node in enumerate(nodes, start=1):
        if isinstance(node, XFade):
            ms = beats_to_seconds(m, node.beats) * 1000 if node.beats is not None else node.ms
            xid = f"x{i}"
            clips.append({"id": xid, "type": "xfade", "length": f"{ms:g}ms", "shape": _SHAPES[node.curve]})
            legacy[xid] = (ms, node.curve)
            continue
        assert isinstance(node, Clip)
        cid = f"n{i}"
        d = {"id": cid, "type": "clip", "source": node.source or source_name,
             "segment": node.segment_name, "index": node.index, "bars": node.bars, "beats": node.beats,
             "offset_bars": node.offset_bars, "offset_beats": node.offset_beats, "loop": node.loop}
        d = {k: v for k, v in d.items() if v is not None}
        probe = ClipNode.model_validate(d)
        s0, s1 = _clip_bounds(probe, m)
        clip_s = (s1 - s0) * (node.loop or 1)
        devices: list[dict] = []
        autos: list[dict] = []
        for k, fx in enumerate(node.fx, start=1):
            _convert_effect(fx, f"{cid}_{k}", clip_s, devices, autos, warnings, cid)
        if devices:
            d["devices"] = devices
        if autos:
            d["automation"] = autos
        clips.append(d)
    plan = Plan.model_validate({
        "version": 2,
        "sources": {source_name: {"file": str(audio_path), "map": str(map_path)}},
        "tracks": [{"id": "main", "clips": clips}],
        "master": {"devices": []},  # the old compositor had no limiter: keep the samples untouched
        "notes": "converted from a legacy composition by recut.legacy",
    })
    return LegacyPlan(plan, legacy, warnings)


def _reverb_device(did: str, fx, dry_wet: float) -> dict:
    preset = PRESETS[fx.reverb_type]
    room = fx.room_size if fx.room_size is not None else preset["room_size"]
    damping = fx.damping if fx.damping is not None else preset["damping"]
    width = fx.width if fx.width is not None else preset["width"]
    rooms, decays = zip(*dev_mod.REVERB_DECAY_TABLE)
    return {"id": did, "type": "reverb", "decay": f"{np.interp(room, rooms, decays):.2f}s", "size": 50,
            "hi_cut": 18000 - 14000 * damping, "width": width * 100, "dry_wet": dry_wet}


def _convert_effect(fx: Effect, did: str, clip_s: float, devices: list, autos: list,
                    warnings: list[str], cid: str) -> None:
    if isinstance(fx, Fade):
        if any(a["target"] == "gain" for a in autos):
            warnings.append(f"{cid}: only the first Fade is kept")
            return
        autos.append({"target": "gain", "from": _db(fx.vol_start), "to": _db(fx.vol_end),
                      "over": f"{clip_s:.6f}s", "at": "start", "shape": _SHAPES[fx.curve]})
    elif isinstance(fx, ReverbSweep):
        devices.append(_reverb_device(did, fx, fx.wetness_start * 100))
        over = fx.duration if fx.duration is not None else clip_s
        autos.append({"target": f"devices.{did}.dry_wet", "from": fx.wetness_start * 100,
                      "to": fx.wetness_end * 100, "over": f"{over:.6f}s", "at": "start",
                      "shape": _SHAPES[fx.curve]})
    elif isinstance(fx, Reverb):
        devices.append(_reverb_device(did, fx, fx.wetness * 100))
    elif isinstance(fx, Delay):
        devices.append({"id": did, "type": "delay", "time": f"{fx.delay_seconds * 1000:g}ms",
                        "feedback": min(fx.feedback * 100, 95), "filter_lo": 20, "filter_hi": 19000,
                        "ping_pong": False, "dry_wet": fx.mix * 100})
    elif isinstance(fx, FilterSweep):
        devices.append({"id": did, "type": "auto_filter",
                        "filter": "lowpass" if fx.filter_type == "low" else "highpass",
                        "frequency": fx.freq_start})
        over = fx.duration if fx.duration is not None else clip_s
        shape = "linear" if fx.curve == 1 else ("exp" if fx.curve > 1 else "log")
        autos.append({"target": f"devices.{did}.frequency", "from": fx.freq_start, "to": fx.freq_end,
                      "over": f"{over:.6f}s", "at": "start", "shape": shape})
    else:  # pragma: no cover - EFFECT_TYPES is closed
        warnings.append(f"{cid}: unknown effect {type(fx).__name__} dropped")


def render_legacy(nodes: list, source_name: str, audio_path: Path, map_path: Path):
    """Convert and render an old-format node list. Returns (Audio, RenderInfo, LegacyPlan)."""
    lp = composition_to_plan(nodes, source_name, audio_path, map_path)
    audio, info = render_plan(lp.plan, Path("."), _legacy_xfades=lp.legacy_xfades)
    return audio, info, lp
