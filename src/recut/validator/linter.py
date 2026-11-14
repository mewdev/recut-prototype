"""A9: musical linter. "Is this a musically sensible cut?" (plan + map, no audio needed).

Runs from `engine.render_plan` once clip bounds and splices are known, and returns contract
`Issue`s with `splice` / `node` ids set. Rules (docs/workstreams/Q-quality.md):

- `phrase_align`: a splice point isn't on a phrase boundary of the outgoing or incoming source
- `ending`: the last clip stops mid-section and has no `fade_out`
- `energy_drop`: loudness falls by more than 6 dB across a splice with no fade or xfade
- `duration`: rendered length misses the target (warn > 2 s, error > 10 %)

Cross-song rules (A5, PLAN §2), keyed by splice id:

- `downbeat` (error, every splice): the join isn't within 30 ms of a downbeat of each source
- `bpm_gap`, `key_compat`, `loudness_jump` (warn, `cross_source` splices only)

Decision: `loudness_jump` is the source-level check (3 s short-term loudness of the outgoing
source before the cut vs the incoming source after it, clip gain included, after the A3 level
match). It does not duplicate `qc_gain_jump`, which measures the rendered audio over 400 ms.
"""

import math
from typing import Optional

import numpy as np

from recut.audio import Audio
from recut.contracts.plan import ClipNode, Plan
from recut.contracts.render import Issue, RenderSegment, Splice
from recut.map.parser import get_segment
from recut.map.schema import EnrichedSegment, MusicMap
from recut.qc import _momentary
from recut.validator.camelot import camelot, keys_compatible

PHRASE_TOL_S = 0.030       # splice point vs phrase/section boundary
ENERGY_DROP_DB = 6.0       # loudness fall across a splice
SMOOTHING_XFADE_MS = 100   # a shorter overlap is a click cover, not an energy smoother
DOWNBEAT_TOL_S = 0.030     # splice point vs a downbeat of each source
BPM_GAP_FRAC = 0.03        # tempo difference (also the tolerance around a 2:1 ratio)
LOUDNESS_WINDOW_S = 3.0    # short-term window either side of a cross-source splice
LOUDNESS_JUMP_DB = 3.0
LOUDNESS_MIN_WINDOW_S = 1.0
DURATION_WARN_S = 2.0
DURATION_ERROR_FRAC = 0.10


def _boundaries(m: MusicMap) -> list[float]:
    """Phrase starts plus section starts/ends (a section edge is a phrase boundary)."""
    out: list[float] = []
    for s in m.segments:
        if s.segment_name == "silence" and s.end - s.start < 1e-3:
            continue
        out += [s.start, s.end, *s.phrases]
    return sorted(out)


def _near(t: float, grid: list[float], tol: float = PHRASE_TOL_S) -> bool:
    return any(abs(t - g) <= tol for g in grid)


def _finite(x: Optional[float]) -> Optional[float]:
    return x if x is not None and math.isfinite(x) else None


def _edge_loudness(seg: EnrichedSegment, at_end: bool, clip_edge: float) -> Optional[float]:
    """Section end/start loudness if the clip reaches that edge, else the section mean."""
    edge = seg.end if at_end else seg.start
    if abs(clip_edge - edge) <= PHRASE_TOL_S:
        return _finite(seg.loudness_db_end if at_end else seg.loudness_db_start)
    return _finite(seg.loudness_db)


def _short_term(audio: Audio, lo: float, hi: float, gain_db: float) -> Optional[float]:
    """Loudness (LUFS) of source seconds [lo, hi] plus clip gain; None if too short or silent."""
    if hi - lo < LOUDNESS_MIN_WINDOW_S:
        return None
    x = audio.samples if audio.samples.ndim == 2 else np.stack([audio.samples, audio.samples])
    a, b = int(max(lo, 0) * audio.sr), int(hi * audio.sr)
    v = _momentary(x, audio.sr, a, min(b, x.shape[-1]))
    return None if v is None else v + gain_db


def _cross_song(sp: Splice, prev: ClipNode, nxt: ClipNode, rp: RenderSegment, rn: RenderSegment,
                maps: dict[str, MusicMap], audio: Optional[dict[str, Audio]]) -> list[Issue]:
    ma, mb = maps[prev.source], maps[nxt.source]
    out: list[Issue] = []
    gap = abs(ma.bpm - mb.bpm) / min(ma.bpm, mb.bpm)
    ratio = max(ma.bpm, mb.bpm) / min(ma.bpm, mb.bpm)
    if gap > BPM_GAP_FRAC and abs(ratio / 2 - 1) > BPM_GAP_FRAC:
        out.append(Issue(severity="warn", rule="bpm_gap", splice=sp.id, node=nxt.id,
                         message=f"{sp.id}: {prev.source!r} {ma.bpm:.0f} BPM → {nxt.source!r} "
                                 f"{mb.bpm:.0f} BPM ({gap * 100:.1f}%)"))
    if ma.key and mb.key:
        ka, kb = camelot(ma.key.tonic, ma.key.mode), camelot(mb.key.tonic, mb.key.mode)
        if ka and kb and not keys_compatible(ka, kb):
            out.append(Issue(severity="warn", rule="key_compat", splice=sp.id, node=nxt.id,
                             message=f"{sp.id}: keys {ma.key.tonic} {ma.key.mode} ({ka[0]}{ka[1]}) → "
                                     f"{mb.key.tonic} {mb.key.mode} ({kb[0]}{kb[1]}) are not "
                                     f"the same, relative or adjacent on the Camelot wheel"))
    if audio and prev.source in audio and nxt.source in audio:
        w = LOUDNESS_WINDOW_S
        a = _short_term(audio[prev.source], max(rp.src_end - w, rp.src_start), rp.src_end, prev.gain)
        b = _short_term(audio[nxt.source], rn.src_start, min(rn.src_start + w, rn.src_end), nxt.gain)
        if a is not None and b is not None and abs(b - a) > LOUDNESS_JUMP_DB:
            out.append(Issue(severity="warn", rule="loudness_jump", splice=sp.id, node=nxt.id,
                             message=f"{sp.id}: short-term loudness jumps {b - a:+.1f} dB across the "
                                     f"splice ({a:.1f} to {b:.1f} LUFS)"))
    return out


def lint_plan(plan: Plan, maps: dict[str, MusicMap], segments: list[RenderSegment],
              splices: list[Splice], duration_s: Optional[float] = None,
              audio: Optional[dict[str, Audio]] = None) -> list[Issue]:
    issues: list[Issue] = []
    clips = {n.id: n for n in plan.tracks[0].clips if isinstance(n, ClipNode)}
    seg_by_node = {s.node_id: s for s in segments}
    grids = {sid: _boundaries(m) for sid, m in maps.items()}

    def section(node: ClipNode) -> Optional[EnrichedSegment]:
        try:
            return get_segment(maps[node.source], node.segment, node.index)
        except ValueError:
            return None

    for sp in splices:
        prev, nxt = clips.get(sp.from_), clips.get(sp.to)
        if prev is None or nxt is None:
            continue
        rp, rn = seg_by_node[prev.id], seg_by_node[nxt.id]
        # downbeat: in output time the incoming clip starts at out_time, where the outgoing
        # source is `overlap` before its clip end; both must sit on a downbeat of their grid.
        # An overlap under SMOOTHING_XFADE_MS is a click cover: the join is the clip edge.
        shift = sp.overlap_ms / 1000 if sp.overlap_ms >= SMOOTHING_XFADE_MS else 0.0
        for side, node, t in (("outgoing", prev, rp.src_end - shift),
                              ("incoming", nxt, rn.src_start)):
            if not _near(t, list(maps[node.source].bars), DOWNBEAT_TOL_S):
                issues.append(Issue(
                    severity="error", rule="downbeat", splice=sp.id, node=nxt.id,
                    message=f"{sp.id}: {side} join at {t:.2f}s of source {node.source!r} is not on a "
                            f"downbeat (within {DOWNBEAT_TOL_S * 1000:.0f} ms)"))
        if sp.cross_source:
            issues += _cross_song(sp, prev, nxt, rp, rn, maps, audio)
        # phrase_align: cut out of `prev` at its src_end, into `nxt` at its src_start
        for side, node, t in (("outgoing", prev, rp.src_end), ("incoming", nxt, rn.src_start)):
            if not _near(t, grids[node.source]):
                issues.append(Issue(
                    severity="warn", rule="phrase_align", splice=sp.id, node=nxt.id,
                    message=f"{sp.id}: {side} cut at {t:.2f}s of source {node.source!r} "
                            f"({node.segment}#{node.index}) is not on a phrase boundary"))
        # energy_drop
        smoothed = (sp.overlap_ms >= SMOOTHING_XFADE_MS or prev.fade_out is not None
                    or nxt.fade_in is not None)
        sa, sb = section(prev), section(nxt)
        if not smoothed and sa and sb:
            a, b = _edge_loudness(sa, True, rp.src_end), _edge_loudness(sb, False, rn.src_start)
            if a is not None and b is not None:
                drop = (a + prev.gain) - (b + nxt.gain)
                if drop > ENERGY_DROP_DB:
                    issues.append(Issue(
                        severity="warn", rule="energy_drop", splice=sp.id, node=nxt.id,
                        message=f"{sp.id}: loudness drops {drop:.1f} dB ({prev.id} → {nxt.id}) "
                                f"with no fade or crossfade"))

    # ending: the last clip stops at a section end / the song's end, or has a fade_out
    if segments:
        last = clips.get(segments[-1].node_id)
        if last is not None and last.fade_out is None:
            m, end = maps[last.source], segments[-1].src_end
            ends = [s.end for s in m.segments if s.end - s.start > 1e-3] + [m.duration]
            if not _near(end, ends):
                issues.append(Issue(
                    severity="warn", rule="ending", node=last.id,
                    message=f"the cut ends mid-section ({last.segment}#{last.index} at {end:.2f}s) "
                            f"with no fade_out"))

    # duration
    target = plan.target_duration_s
    if target and duration_s is not None:
        diff = duration_s - target
        if abs(diff) > DURATION_WARN_S:
            err = abs(diff) > DURATION_ERROR_FRAC * target
            issues.append(Issue(
                severity="error" if err else "warn", rule="duration",
                message=f"duration {duration_s:.1f}s vs target {target:.0f}s ({diff:+.1f}s)"))
    return issues
