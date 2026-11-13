"""Timeline renderer for plan.json v2 (thin slice of workstream A).

Places clips on a timeline buffer and sums overlaps (instead of concatenating), applies
clip gain, fade handles and xfade joins, then the master limiter, and reports what it did
as RenderInfo (render.json).

Implemented here: sources, single track, clip selection/loop/gain/fade handles, xfade
(length, shape, out_shape/in_shape incl. "hold"), master limiter, legacy validator.
Not yet rendered (reported as `not_rendered` warnings): devices, sends/returns,
automation, track volume/pan → tasks A7/A8.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
from pedalboard import Limiter, Pedalboard  # type: ignore

from recut.audio import Audio
from recut.compositor.nodes import Clip, XFade
from recut.contracts.plan import ClipNode, Plan, Ramp, XFadeNode
from recut.contracts.render import Issue, RenderInfo, RenderSegment, SourceInfo, Splice
from recut.contracts.units import db_to_gain, parse_time, ramp_in
from recut.map.parser import bars_to_seconds, beats_to_seconds, get_segment, parse_recut_map
from recut.map.schema import MusicMap
from recut.validator import validate
from recut.validator.rules import RULES


class PlanError(ValueError):
    """The plan can't be rendered (bad section, too many bars, ...). Message is agent-facing."""


@dataclass
class LoadedSource:
    music_map: MusicMap
    audio: Audio


_CACHE: dict[tuple[str, float], object] = {}


def _cached(path: Path, loader):
    key = (str(path.resolve()), path.stat().st_mtime)
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
        out[sid] = LoadedSource(music_map, audio)
    return out


def _clip_bounds(node: ClipNode, m: MusicMap) -> tuple[float, float]:
    try:
        seg = get_segment(m, node.segment, node.index)
    except ValueError as e:
        names = sorted({s.segment_name for s in m.segments if s.segment_name != "silence"})
        raise PlanError(f"clip {node.id}: {e}. Sections in source {node.source!r}: {names}") from e
    start, end = seg.start, seg.end
    if node.offset_bars is not None:
        start += bars_to_seconds(m, node.offset_bars)
    elif node.offset_beats is not None:
        start += beats_to_seconds(m, node.offset_beats)
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


def render_plan(plan: Plan, base_dir: Path) -> tuple[Audio, RenderInfo]:
    if len(plan.tracks) > 1:
        raise PlanError("multi-track not supported yet")
    sources = load_sources(plan, base_dir)
    sr = next(iter(sources.values())).audio.sr
    track = plan.tracks[0]
    issues: list[Issue] = []

    placed: list[tuple[int, np.ndarray]] = []  # (start sample, samples)
    segments: list[RenderSegment] = []
    splices: list[Splice] = []
    spans_auto = []
    cursor = 0
    pending: XFadeNode | None = None
    prev_node: ClipNode | None = None

    for node in track.clips:
        if isinstance(node, XFadeNode):
            pending = node
            continue
        src = sources[node.source]
        m = src.music_map
        s0, s1 = _clip_bounds(node, m)
        a, b = int(round(s0 * sr)), int(round(s1 * sr))
        clip = src.audio.samples[:, a:b].copy()
        if node.loop:
            clip = np.concatenate([clip] * node.loop, axis=-1)
        clip *= db_to_gain(node.gain)
        n_len = clip.shape[-1]
        if node.fade_in:
            k = min(n_len, int(parse_time(node.fade_in.length, m.bpm, m.beats_per_bar) * sr))
            clip[:, :k] *= ramp_in(node.fade_in.shape, k)
        if node.fade_out:
            k = min(n_len, int(parse_time(node.fade_out.length, m.bpm, m.beats_per_bar) * sr))
            clip[:, n_len - k:] *= ramp_in(node.fade_out.shape, k)[::-1]

        overlap = 0
        if pending is not None and placed:
            want = int(parse_time(pending.length, m.bpm, m.beats_per_bar) * sr)
            prev_start, prev = placed[-1]
            overlap = min(want, prev.shape[-1] - 1, n_len - 1)
            if overlap < want:
                issues.append(Issue(severity="warn", rule="xfade_clamped", node=pending.id,
                                    message=f"xfade {pending.id} shortened to {overlap / sr * 1000:.0f} ms (a clip is shorter than the requested {pending.length})"))
            if overlap > 0:
                prev[:, prev.shape[-1] - overlap:] *= ramp_in(pending.shape_out, overlap)[::-1]
                clip[:, :overlap] *= ramp_in(pending.shape_in, overlap)
        start = cursor - overlap

        if prev_node is not None:
            splices.append(Splice(
                id=f"s{len(splices) + 1}", out_time=start / sr, from_=prev_node.id, to=node.id,
                cross_source=prev_node.source != node.source, overlap_ms=overlap / sr * 1000,
                out_shape=pending.shape_out if pending and overlap else None,
                in_shape=pending.shape_in if pending and overlap else None,
            ))
        placed.append((start, clip))
        segments.append(RenderSegment(
            node_id=node.id, source=node.source, label=f"{node.segment}#{node.index}",
            src_start=s0, src_end=s1, out_start=start / sr, out_end=(start + n_len) / sr,
        ))
        for au in node.automation:
            if isinstance(au, Ramp):
                over = parse_time(au.over, m.bpm, m.beats_per_bar)
                rel = 0.0 if au.at == "start" else (n_len / sr - over if au.at == "end"
                                                     else parse_time(au.at, m.bpm, m.beats_per_bar))
                spans_auto.append(dict(node_id=node.id, target=au.target,
                                       out_start=start / sr + rel, out_end=start / sr + rel + over))
        unrendered = [w for w, v in (("devices", node.devices), ("sends", node.sends),
                                     ("automation", node.automation)) if v]
        if unrendered:
            issues.append(Issue(severity="warn", rule="not_rendered", node=node.id,
                                message=f"clip {node.id}: {', '.join(unrendered)} not rendered yet (engine tasks A7/A8) — preview plays it dry"))
        cursor = start + n_len
        prev_node, pending = node, None

    for what, present in (("track devices/automation", track.devices or track.automation),
                          ("track volume/pan", track.volume not in (0, 0.0) or track.pan != 0),
                          ("returns", plan.returns)):
        if present:
            issues.append(Issue(severity="warn", rule="not_rendered",
                                message=f"{what} not rendered yet (engine tasks A7/A8)"))

    total = max(s + c.shape[-1] for s, c in placed)
    mix = np.zeros((2, total), dtype=np.float32)
    for s, c in placed:
        mix[:, s:s + c.shape[-1]] += c

    peak = float(np.abs(mix).max()) if total else 0.0
    peak_db = 20 * math.log10(peak) if peak > 0 else -math.inf
    limited = False
    for dev in plan.master.devices:
        if dev.type == "limiter" and peak_db > dev.ceiling:
            # pedalboard's (JUCE) Limiter normalizes its output to 0 dBFS → scale to the ceiling
            mix = Pedalboard([Limiter(threshold_db=dev.ceiling)])(mix, sr) * (10 ** (dev.ceiling / 20))
            limited = True
        elif dev.type != "limiter":
            issues.append(Issue(severity="warn", rule="not_rendered",
                                message=f"master device {dev.id} ({dev.type}) not rendered yet"))
    # only flag clipping the edit created (overlaps), not a source that is already hot
    clip_peak = max(float(np.abs(c).max()) for _, c in placed)
    if peak_db > 0 and peak > clip_peak * 1.06:
        issues.append(Issue(severity="warn", rule="peak_clip",
                            message=f"overlapping audio sums to {peak_db:+.1f} dBFS before the master chain"))

    issues = _validator_issues(plan, sources) + issues
    if plan.target_duration_s:
        diff = total / sr - plan.target_duration_s
        if abs(diff) > 2.0:
            issues.append(Issue(severity="warn", rule="duration",
                                message=f"duration {total / sr:.1f}s vs target {plan.target_duration_s:.0f}s ({diff:+.1f}s)"))

    info = RenderInfo(
        duration_s=total / sr,
        segments=segments,
        splices=splices,
        issues=issues,
        sources={
            sid: SourceInfo(
                bpm=s.music_map.bpm,
                key=f"{s.music_map.key.tonic} {s.music_map.key.mode}" if s.music_map.key else None,
                duration_s=s.audio.samples.shape[-1] / sr,
            )
            for sid, s in sources.items()
        },
        automation=spans_auto,
        peak_dbfs=peak_db if peak > 0 else -120.0,
        limiter_applied=limited,
    )
    return Audio(mix, sr), info
