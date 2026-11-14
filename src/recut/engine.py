"""Timeline renderer for plan.json v2 (workstream A: A1-A4, A7, A8).

Places clips on a timeline buffer and sums overlaps (instead of concatenating), applies
clip gain, fade handles and xfade joins, routes clip sends into return tracks (each
return's device chain runs once over the whole timeline and rings out past the last clip),
applies track volume/pan, then the master chain, and reports what it did as RenderInfo
(render.json). Gain/send/device-parameter automation is rendered per sample (see
recut.automation); devices live in recut.devices.

Features the engine does not render yet are reported as `not_rendered` warnings.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

from recut import devices as dev_mod
from recut.audio import Audio
from recut.automation import AutomationError, build_curve, span_seconds
from recut.compositor.nodes import Clip, XFade
from recut.contracts.plan import ClipNode, Plan, XFadeNode
from recut.contracts.render import (
    AutomationSpan,
    Issue,
    RenderInfo,
    RenderSegment,
    SourceInfo,
    Splice,
)
from recut.contracts.units import db_to_gain, parse_time, ramp_in
from recut.map.parser import bars_to_seconds, beats_to_seconds, get_segment, parse_recut_map
from recut.map.schema import MusicMap
from recut.primitives.curves import make_envelope
from recut.qc import RenderInfoQC, integrated_lufs, run_qc
from recut.validator import validate
from recut.validator.linter import lint_plan
from recut.validator.rules import RULES


class PlanError(ValueError):
    """The plan can't be rendered (bad section, too many bars, ...). Message is agent-facing."""


@dataclass
class LoadedSource:
    music_map: MusicMap
    audio: Audio
    lufs_in: float | None = None      # integrated loudness of the file as loaded
    lufs_target: float | None = None  # what it was matched to (== lufs_in when no gain applied)


LUFS_CAP = -9.0        # multi-source target never exceeds this: a loud master is not made louder
LUFS_MIN_GAIN_DB = 0.05  # smaller corrections are skipped (leaves the samples untouched)

_CACHE: dict[tuple, object] = {}


def _cached(path: Path, loader, tag: str = "load"):
    key = (tag, str(path.resolve()), path.stat().st_mtime)
    if key not in _CACHE:
        _CACHE[key] = loader(path)
    return _CACHE[key]


def _load_audio(path: Path) -> Audio:
    audio = Audio.load(str(path))
    samples = audio.samples
    if samples.ndim == 1:
        samples = np.stack([samples, samples])
    return Audio(samples.astype(np.float32), audio.sr)


def load_sources(plan: Plan, base_dir: Path) -> dict[str, LoadedSource]:
    out: dict[str, LoadedSource] = {}
    target_sr = None
    for sid, ref in plan.sources.items():
        audio_path, map_path = base_dir / ref.file, base_dir / ref.map
        for p in (audio_path, map_path):
            if not p.exists():
                raise PlanError(f"source {sid!r}: file not found: {p}")
        audio = _cached(audio_path, _load_audio)
        music_map = _cached(map_path, parse_recut_map)
        target_sr = target_sr or audio.sr
        if audio.sr != target_sr:
            audio = Audio(librosa.resample(audio.samples, orig_sr=audio.sr, target_sr=target_sr), target_sr)
        lufs = _cached(audio_path, lambda _p, a=audio: integrated_lufs(a.samples, a.sr), tag="lufs")
        out[sid] = LoadedSource(music_map, audio, lufs_in=lufs, lufs_target=lufs)
    match_loudness(out)
    return out


def match_loudness(sources: dict[str, LoadedSource]) -> None:
    """Level-match a multi-source plan (PLAN §2 Loudness): every source is gained to one
    common integrated loudness, the loudest source's LUFS capped at LUFS_CAP, so the quiet
    ones come up to it and a loud master is never made louder (it may come down to the cap).
    A single-source plan is left byte-identical. Gain is applied to a copy of the samples."""
    measured = {sid: s.lufs_in for sid, s in sources.items() if s.lufs_in is not None}
    if len(sources) < 2 or not measured:
        return
    target = min(max(measured.values()), LUFS_CAP)
    for sid, lufs in measured.items():
        src = sources[sid]
        src.lufs_target = target
        gain_db = target - lufs
        if abs(gain_db) >= LUFS_MIN_GAIN_DB:
            src.audio = Audio((src.audio.samples * db_to_gain(gain_db)).astype(np.float32), src.audio.sr)


def _clip_bounds(node: ClipNode, m: MusicMap) -> tuple[float, float]:
    try:
        seg = get_segment(m, node.segment, node.index)
    except ValueError as e:
        names = sorted({s.segment_name for s in m.segments if s.segment_name != "silence"})
        raise PlanError(f"clip {node.id}: {e}. Sections in source {node.source!r}: {names}") from e
    start, end = seg.start, seg.end
    # offsets count from the first downbeat: the first segment starts at 0.0, before it
    # (pickup / lead-in), and the lead-in is not a bar
    origin = seg.downbeats[0] if seg.downbeats and seg.downbeats[0] > start else start
    if node.offset_bars is not None:
        start = origin + bars_to_seconds(m, node.offset_bars)
    elif node.offset_beats is not None:
        start = origin + beats_to_seconds(m, node.offset_beats)
    if start >= end - 1e-6:
        raise PlanError(f"clip {node.id}: offset is past the end of {node.segment}#{node.index}")
    length = None
    if node.bars is not None:
        length = bars_to_seconds(m, node.bars)
    elif node.beats is not None:
        length = beats_to_seconds(m, node.beats)
    if length is not None:
        if start + length > end + 0.05:  # 50 ms slack for beat-grid rounding
            avail_bars = (end - start) / bars_to_seconds(m, 1)
            raise PlanError(
                f"clip {node.id}: {node.segment}#{node.index} has only {avail_bars:.2f} bars "
                f"left after the offset; asked for {node.bars or node.beats} "
                f"{'bars' if node.bars is not None else 'beats'}"
            )
        end = min(start + length, end)
    return start, end


def _legacy_nodes(clips: list) -> list:
    out = []
    for n in clips:
        if isinstance(n, ClipNode):
            c = Clip(n.segment, index=n.index, source=n.source, bars=n.bars, beats=n.beats,
                     offset_bars=n.offset_bars, offset_beats=n.offset_beats, loop=n.loop)
            c._plan_id = n.id  # type: ignore[attr-defined]
            out.append(c)
        else:
            out.append(XFade(ms=10))
    return out


def _validator_issues(plan: Plan, sources: dict[str, LoadedSource]) -> list[Issue]:
    """Existing structural rules. Sequence rules (start/end boundaries) only for one source."""
    clips = [n for n in plan.tracks[0].clips if isinstance(n, ClipNode)]
    multi = len({n.source for n in clips}) > 1
    results = []
    if multi:
        for n in clips:
            for rule in RULES:
                r = rule.check(_legacy_nodes([n])[0], sources[n.source].music_map)
                if r:
                    results.append(r)
    else:
        results = validate(sources[clips[0].source].music_map, *_legacy_nodes(plan.tracks[0].clips))
    return [
        Issue(severity="warn" if r.severity == "warning" else r.severity, rule="structure",
              message=r.message, node=getattr(r.node, "_plan_id", None))
        for r in results
    ]


TAIL_FLOOR_DB = -60.0  # return tails are cut where they fall below this level
TAIL_MAX_S = 10.0      # ...or this many seconds after the last clip
TAIL_FLOOR = 10 ** (TAIL_FLOOR_DB / 20)


@dataclass
class _Placed:
    node: ClipNode
    start: int
    samples: np.ndarray  # (2, n) after gain, fades and devices; xfade ramps are applied in place
    tail: np.ndarray  # (2, m) device tail (reverb/delay) ringing after the clip, not part of the layout
    sends: dict[str, "np.ndarray | float"]
    bpm: float


def _legacy_overlap(ms: float, curve: str, sr: int, n_prev: int, n_next: int):
    """Old-format xfade: overlap = int(ms * sr / 1000) and curve pair from make_envelope."""
    n = int(ms * sr / 1000)
    if n >= n_prev or n >= n_next:
        raise ValueError(f"xfade_ms={ms} longer than one segment (a={n_prev} samples, b={n_next} samples)")
    return n, make_envelope(1.0, 0.0, n, curve), make_envelope(0.0, 1.0, n, curve)  # type: ignore[arg-type]


def _check_targets(autos, owner: str, device_ids: dict[str, object], return_ids: set[str]) -> None:
    for au in autos:
        t = au.target
        ok = t == "gain" or (t.startswith("sends.") and t[6:] in return_ids)
        if not ok and t.startswith("devices."):
            parts = t.split(".")
            d = device_ids.get(parts[1]) if len(parts) == 3 else None
            ok = d is not None and parts[2] in dev_mod.AUTOMATABLE.get(d.type, {})
            if d is not None and not ok:
                raise PlanError(f"{owner}: {t!r} can't be automated. {d.type} parameters you can automate: "
                                f"{sorted(dev_mod.AUTOMATABLE.get(d.type, {})) or 'none'}")
            if not ok:
                hint = (f" Devices here: {sorted(device_ids)}" if device_ids else
                        f" {owner} has no devices")
                raise PlanError(f"{owner}: automation target {t!r} is not a parameter of a device on it.{hint}")
        if not ok:
            raise PlanError(f"{owner}: unknown automation target {t!r}. Use 'gain', 'sends.<return id>' "
                            f"(returns: {sorted(return_ids) or 'none'}) or 'devices.<device id>.<parameter>'")


def _pan(x: np.ndarray, pan: float) -> np.ndarray:
    """Constant-power pan, pan in -50 (L) … 50 (R); unity at the centre."""
    angle = (pan / 50 + 1) * math.pi / 4
    out = x.copy()
    out[0] *= math.sqrt(2) * math.cos(angle)
    out[1] *= math.sqrt(2) * math.sin(angle)
    return out


def render_plan(plan: Plan, base_dir: Path, *, _legacy_xfades: dict[str, tuple[float, str]] | None = None,
                deep_qc: bool = True) -> tuple[Audio, RenderInfo]:
    """Render a plan to audio + render.json info.

    `deep_qc=False` skips the Essentia detectors (basic ones run; `info._deep()` runs the rest later).

    `_legacy_xfades` is internal (set by recut.legacy for old saved compositions): it maps an
    xfade node id to (ms, curve) so the old `qsin` fade-out (1 - sin, equal-gain) and the
    old overlap length are reproduced exactly; the v2 contract has no shape for that.
    """
    if len(plan.tracks) > 1:
        raise PlanError("multi-track not supported yet")
    legacy = _legacy_xfades or {}
    sources = load_sources(plan, base_dir)
    sr = next(iter(sources.values())).audio.sr
    first_map = next(iter(sources.values())).music_map
    bpm0, bpb0 = first_map.bpm, first_map.beats_per_bar
    track = plan.tracks[0]
    return_ids = {r.id for r in plan.returns}
    issues: list[Issue] = []

    placed: list[_Placed] = []
    segments: list[RenderSegment] = []
    splices: list[Splice] = []
    spans_auto: list[AutomationSpan] = []
    cursor = 0
    pending: XFadeNode | None = None
    prev_node: ClipNode | None = None

    for node in track.clips:
        if isinstance(node, XFadeNode):
            pending = node
            continue
        src = sources[node.source]
        m = src.music_map
        bpm, bpb = m.bpm, m.beats_per_bar
        s0, s1 = _clip_bounds(node, m)
        a, b = int(round(s0 * sr)), int(round(s1 * sr))
        clip = src.audio.samples[:, a:b].copy()
        if node.loop:
            clip = np.concatenate([clip] * node.loop, axis=-1)
        n_len = clip.shape[-1]
        _check_targets(node.automation, f"clip {node.id}", {d.id: d for d in node.devices}, return_ids)
        try:
            gain = build_curve(node.automation, "gain", n_len, sr, bpm, bpb, "level")
            send_curves: dict[str, np.ndarray | float] = {}
            for rid in return_ids:
                base = db_to_gain(node.sends.get(rid, "-inf"))
                curve = build_curve(node.automation, f"sends.{rid}", n_len, sr, bpm, bpb, "level")
                if curve is not None or base > 0:
                    send_curves[rid] = base if curve is None else curve
        except AutomationError as e:
            raise PlanError(f"clip {node.id}: {e}") from e
        clip *= db_to_gain(node.gain) if gain is None else gain
        if node.fade_in:
            k = min(n_len, int(parse_time(node.fade_in.length, bpm, bpb) * sr))
            clip[:, :k] *= ramp_in(node.fade_in.shape, k)
        if node.fade_out:
            k = min(n_len, int(parse_time(node.fade_out.length, bpm, bpb) * sr))
            clip[:, n_len - k:] *= ramp_in(node.fade_out.shape, k)[::-1]
        tail = np.zeros((2, 0), dtype=np.float32)
        if node.devices:  # insert chain after fades; reverb/delay tails ring on past the clip
            est = int(dev_mod.tail_seconds(node.devices, bpm, bpb) * sr)
            padded = np.concatenate([clip, np.zeros((2, est), dtype=clip.dtype)], axis=-1)
            try:
                out = dev_mod.apply_devices(node.devices, padded,
                                            dev_mod.Ctx(sr, bpm, bpb, n_len / sr, node.automation))
            except AutomationError as e:
                raise PlanError(f"clip {node.id}: {e}") from e
            clip = out[:, :n_len].copy()
            loud = np.nonzero(np.abs(out[:, n_len:]).max(axis=0) > TAIL_FLOOR)[0]
            if loud.size:
                tail = out[:, n_len: n_len + int(loud[-1]) + 1].copy()

        overlap = 0
        if pending is not None and placed:
            prev = placed[-1]
            if pending.id in legacy:
                overlap, out_ramp, in_ramp = _legacy_overlap(*legacy[pending.id], sr, prev.samples.shape[-1], n_len)
                want = overlap
            else:
                want = int(parse_time(pending.length, bpm, bpb) * sr)
                overlap = min(want, prev.samples.shape[-1] - 1, n_len - 1)
                out_ramp = ramp_in(pending.shape_out, overlap)[::-1]
                in_ramp = ramp_in(pending.shape_in, overlap)
            if overlap < want:
                issues.append(Issue(severity="warn", rule="xfade_clamped", node=pending.id,
                                    message=f"xfade {pending.id} shortened to {overlap / sr * 1000:.0f} ms (a clip is shorter than the requested {pending.length})"))
            if overlap > 0:
                prev.samples[:, prev.samples.shape[-1] - overlap:] *= out_ramp
                clip[:, :overlap] *= in_ramp
        start = cursor - overlap

        if prev_node is not None:
            splices.append(Splice(
                id=f"s{len(splices) + 1}", out_time=start / sr, from_=prev_node.id, to=node.id,
                cross_source=prev_node.source != node.source, overlap_ms=overlap / sr * 1000,
                out_shape=(legacy[pending.id][1] if pending.id in legacy else pending.shape_out)
                if pending and overlap else None,
                in_shape=(legacy[pending.id][1] if pending.id in legacy else pending.shape_in)
                if pending and overlap else None,
            ))
        placed.append(_Placed(node, start, clip, tail, send_curves, bpm))
        segments.append(RenderSegment(
            node_id=node.id, source=node.source, label=f"{node.segment}#{node.index}",
            src_start=s0, src_end=s1, out_start=start / sr, out_end=(start + n_len) / sr,
        ))
        for au in node.automation:
            rel0, rel1 = span_seconds(au, bpm, bpb, n_len / sr)
            spans_auto.append(AutomationSpan(node_id=node.id, target=au.target,
                                             out_start=start / sr + rel0, out_end=start / sr + rel1))
        cursor = start + n_len
        prev_node, pending = node, None

    timeline = max(p.start + p.samples.shape[-1] for p in placed)
    extent = max(p.start + p.samples.shape[-1] + p.tail.shape[-1] for p in placed)
    pad = int(TAIL_MAX_S * sr)

    # ---- track: sum clips, devices, volume, pan ------------------------------------------
    bus = np.zeros((2, extent + pad), dtype=np.float32)
    returns_in = {rid: np.zeros((2, extent + pad), dtype=np.float32) for rid in return_ids}
    for p in placed:
        n = p.samples.shape[-1]
        m = p.tail.shape[-1]
        full = np.concatenate([p.samples, p.tail], axis=-1) if m else p.samples
        bus[:, p.start:p.start + n + m] += full
        for rid, g in p.sends.items():
            if m and isinstance(g, np.ndarray):
                g = np.concatenate([g, np.full(m, g[-1])])
            returns_in[rid][:, p.start:p.start + n + m] += full * g

    _check_targets(track.automation, f"track {track.id}", {d.id: d for d in track.devices}, return_ids)
    try:
        tgain = build_curve(track.automation, "gain", extent + pad, sr, bpm0, bpb0, "level", timeline / sr)
    except AutomationError as e:
        raise PlanError(f"track {track.id}: {e}") from e
    ctx = dev_mod.Ctx(sr, bpm0, bpb0, timeline / sr, track.automation)
    bus = dev_mod.apply_devices(track.devices, bus, ctx)
    bus = bus * (db_to_gain(track.volume) if tgain is None else tgain)
    if track.pan:
        bus = _pan(bus, track.pan)
    for au in track.automation:
        rel0, rel1 = span_seconds(au, bpm0, bpb0, timeline / sr)
        spans_auto.append(AutomationSpan(node_id=track.id, target=au.target, out_start=rel0, out_end=rel1))

    # ---- returns: one device chain over the whole send buffer, tails ring out ------------
    tail_end = 0
    mix_parts = [bus]
    for r in plan.returns:
        buf = returns_in[r.id]
        if not np.any(buf):
            continue
        _check_targets(r.automation, f"return {r.id}", {d.id: d for d in r.devices}, return_ids)
        rctx = dev_mod.Ctx(sr, bpm0, bpb0, timeline / sr, r.automation)
        out = dev_mod.apply_devices(r.devices, buf, rctx)
        try:
            rgain = build_curve(r.automation, "gain", out.shape[-1], sr, bpm0, bpb0, "level", timeline / sr)
        except AutomationError as e:
            raise PlanError(f"return {r.id}: {e}") from e
        out = out * (db_to_gain(r.volume) if rgain is None else rgain)
        for au in r.automation:
            rel0, rel1 = span_seconds(au, bpm0, bpb0, timeline / sr)
            spans_auto.append(AutomationSpan(node_id=r.id, target=au.target, out_start=rel0, out_end=rel1))
        loud = np.nonzero(np.abs(out).max(axis=0) > TAIL_FLOOR)[0]
        if loud.size:
            tail_end = max(tail_end, int(loud[-1]) + 1)
        mix_parts.append(out.astype(np.float32))

    total = max(extent, tail_end)
    mix = sum(part[:, :total] for part in mix_parts[1:]) + bus[:, :total] if len(mix_parts) > 1 else bus[:, :total]
    mix = np.ascontiguousarray(mix, dtype=np.float32)

    # ---- master ------------------------------------------------------------------------
    mctx = dev_mod.Ctx(sr, bpm0, bpb0, total / sr)
    pre_master = mix
    mix = dev_mod.apply_devices(plan.master.devices, mix, mctx)
    peak = float(np.abs(mix).max()) if total else 0.0
    issues = _validator_issues(plan, sources) + issues
    issues += lint_plan(plan, {sid: s.music_map for sid, s in sources.items()}, segments, splices,
                        total / sr, audio={sid: s.audio for sid, s in sources.items()})

    info = RenderInfoQC(
        duration_s=total / sr,
        segments=segments,
        splices=splices,
        issues=issues,
        sources={
            sid: SourceInfo(
                bpm=s.music_map.bpm,
                key=f"{s.music_map.key.tonic} {s.music_map.key.mode}" if s.music_map.key else None,
                duration_s=s.audio.samples.shape[-1] / sr,
                lufs_in=None if s.lufs_in is None else round(s.lufs_in, 2),
                lufs_target=None if s.lufs_target is None else round(s.lufs_target, 2),
            )
            for sid, s in sources.items()
        },
        automation=spans_auto,
        returns_tail_end=tail_end / sr if tail_end else None,
        peak_dbfs=20 * math.log10(peak) if peak > 0 else -120.0,
        limiter_applied=mctx.limited,
    )
    out = Audio(mix, sr)
    fade_outs = [(seg.out_end - parse_time(p.node.fade_out.length, p.bpm, sources[p.node.source].music_map.beats_per_bar), seg.out_end)
                 for p, seg in zip(placed, segments) if p.node.fade_out]
    info.issues += run_qc(out, info, pre_master=pre_master,
                          sources={sid: s.audio for sid, s in sources.items()}, fade_outs=fade_outs,
                          trim_db=mctx.trim_db, deep=deep_qc)
    return out, info
