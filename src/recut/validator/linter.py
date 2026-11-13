"""A9: musical linter. "Is this a musically sensible cut?" (plan + map, no audio needed).

Runs from `engine.render_plan` once clip bounds and splices are known, and returns contract
`Issue`s with `splice` / `node` ids set. Rules (docs/workstreams/Q-quality.md):

- `phrase_align`: a splice point isn't on a phrase boundary of the outgoing or incoming source
- `ending`: the last clip stops mid-section and has no `fade_out`
- `energy_drop`: loudness falls by more than 6 dB across a splice with no fade or xfade
- `duration`: rendered length misses the target (warn > 2 s, error > 10 %)
"""

import math
from typing import Optional

from recut.contracts.plan import ClipNode, Plan
from recut.contracts.render import Issue, RenderSegment, Splice
from recut.map.parser import get_segment
from recut.map.schema import EnrichedSegment, MusicMap

PHRASE_TOL_S = 0.030       # splice point vs phrase/section boundary
ENERGY_DROP_DB = 6.0       # loudness fall across a splice
SMOOTHING_XFADE_MS = 100   # a shorter overlap is a click cover, not an energy smoother
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


def lint_plan(plan: Plan, maps: dict[str, MusicMap], segments: list[RenderSegment],
              splices: list[Splice], duration_s: Optional[float] = None) -> list[Issue]:
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
