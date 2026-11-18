"""A9: musical linter. "Is this a musically sensible cut?" (plan + map, no audio needed).

Runs from `engine.render_plan` once clip bounds and splices are known, and returns contract
`Issue`s with `splice` / `node` ids set. Rules (docs/workstreams/Q-quality.md):

- `phrase_align`: a splice point isn't on a phrase boundary of the outgoing or incoming source
- `ending`: the last clip stops mid-section and has no `fade_out`
- `energy_drop`: loudness falls by more than 6 dB across a splice with no fade or xfade
- `duration`: rendered length misses the target (warn > 2 s, error > 10 %)
- `ending_drums` (M3, needs `instrument_activity`): the cut ends with a `fade_out` while drum
  activity in the last bar before the fade is above 0.6: the fade switches a busy groove off
- `mid_vocal` (M3, needs `instrument_activity`): a splice lands inside a vocal range, more than
  one beat from the range's edges: it cuts a phrase in half
  (both skip silently when the map has no activity)
- `song_change_gap` (song change only): audible silence (below -50 dBFS) between the outgoing
  song's tail and the incoming song's first sound, gap nodes included: info with the number,
  warn above 2 s (dancers wait for the next song; a requested pause is the exception)

Joins that are not edits are not judged as edits:
- contiguous (same source, the song plays on, no overlap, same gain, no fades): no splice rule
- song change (the outgoing clip reaches its song's end, the incoming starts at its song's
  beginning): no `downbeat`, `phrase_align`, `mid_vocal`, `energy_drop` or cross-song rule
  (one song ending and another starting is not a beat-matched join); `song_change_gap` instead

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
from recut.contracts.units import level_db
from recut.map.activity import bar_seconds
from recut.map.helpers import key_at
from recut.map.musicdata import segment_mean
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
DRUMS_BUSY = 0.6           # mean drum activity in the last bar before a fade-out
SONG_GAP_DB = -50.0        # below this (dBFS RMS, 50 ms windows) a song change is "silence"
SONG_GAP_WARN_S = 2.0      # shipped song changes measured 0.5-1.4 s of it, rejected ones 2.8-2.9 s
SONG_GAP_WINDOW_S = 0.05


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


def _mid_vocal(m: MusicMap, t: float) -> Optional[tuple[float, float]]:
    """The vocal range `t` sits inside, more than one beat from both edges (None otherwise,
    including when the map has no vocal activity)."""
    ia = m.instrument_activity
    if ia is None or ia.vocal is None:
        return None
    beat = 60.0 / m.bpm if m.bpm > 0 else 0.5
    for a, b in ia.vocal.ranges:
        if a + beat < t < b - beat:
            return a, b
    return None


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
    # the key in force at the join in each source (key_ranges when the map has them, else the
    # global key): a song that modulates is judged by where it's actually cut
    a_key, b_key = key_at(ma, rp.src_end), key_at(mb, rn.src_start)
    if a_key and b_key:
        ka, kb = camelot(*a_key), camelot(*b_key)
        if ka and kb and not keys_compatible(ka, kb):
            out.append(Issue(severity="warn", rule="key_compat", splice=sp.id, node=nxt.id,
                             message=f"{sp.id}: keys {a_key[0]} {a_key[1]} ({ka[0]}{ka[1]}) → "
                                     f"{b_key[0]} {b_key[1]} ({kb[0]}{kb[1]}) are not "
                                     f"the same, relative or adjacent on the Camelot wheel"))
    if audio and prev.source in audio and nxt.source in audio:
        w = LOUDNESS_WINDOW_S
        a = _short_term(audio[prev.source], max(rp.src_end - w, rp.src_start), rp.src_end, level_db(prev.gain))
        b = _short_term(audio[nxt.source], rn.src_start, min(rn.src_start + w, rn.src_end), level_db(nxt.gain))
        if a is not None and b is not None and abs(b - a) > LOUDNESS_JUMP_DB:
            out.append(Issue(severity="warn", rule="loudness_jump", splice=sp.id, node=nxt.id,
                             message=f"{sp.id}: short-term loudness jumps {b - a:+.1f} dB across the "
                                     f"splice ({a:.1f} to {b:.1f} LUFS)"))
    return out



def _music_span(m: MusicMap) -> tuple[float, float]:
    """Start of the first and end of the last section that isn't `silence`."""
    music = [s for s in m.segments if s.segment_name != "silence" and s.end - s.start > 1e-3]
    return (music[0].start, music[-1].end) if music else (0.0, m.duration)


def _bar_s(m: MusicMap) -> float:
    return 60.0 / m.bpm * m.beats_per_bar if m.bpm else 2.0


def _is_song_change(rp: RenderSegment, rn: RenderSegment, maps: dict[str, MusicMap]) -> bool:
    """The outgoing clip plays its song to the end (within a bar of the last music) and the
    incoming one starts its song (within a bar of the first music)."""
    ma, mb = maps[rp.source], maps[rn.source]
    return (rp.src_end >= _music_span(ma)[1] - _bar_s(ma)
            and rn.src_start <= _music_span(mb)[0] + _bar_s(mb))


def _is_contiguous(prev: ClipNode, nxt: ClipNode, rp: RenderSegment, rn: RenderSegment,
                   sp: Splice) -> bool:
    """The song simply plays on: same source, sample-contiguous, nothing changes at the join."""
    return (prev.source == nxt.source and sp.overlap_ms <= 0 and abs(rp.src_end - rn.src_start) < 1e-3
            and level_db(prev.gain) == level_db(nxt.gain) and prev.fade_out is None and nxt.fade_in is None)


def _quiet_s(audio: Audio, t: float, gain_db: float, before: bool, limit_s: float = 10.0) -> float:
    """Seconds of audio quieter than SONG_GAP_DB right before (or after) source time `t`."""
    x = np.atleast_2d(audio.samples)
    sr, w = audio.sr, max(1, int(SONG_GAP_WINDOW_S * audio.sr))
    a, b = (max(0.0, t - limit_s), t) if before else (t, t + limit_s)
    seg = np.abs(x[:, int(a * sr): int(b * sr)]).max(axis=0)
    n = seg.size // w
    if n == 0:
        return 0.0
    blocks = seg[: n * w].reshape(n, w) if not before else seg[seg.size - n * w:].reshape(n, w)
    rms_db = 10 * np.log10(np.maximum((blocks.astype(np.float64) ** 2).mean(axis=1), 1e-20)) + gain_db
    quiet = rms_db < SONG_GAP_DB
    if before:
        quiet = quiet[::-1]
    run = int(np.argmin(quiet)) if not quiet.all() else n
    return run * w / sr


def _song_change_gap(prev: ClipNode, nxt: ClipNode, rp: RenderSegment, rn: RenderSegment,
                     audio: Optional[dict[str, Audio]]) -> list[Issue]:
    if not audio or prev.source not in audio or nxt.source not in audio:
        return []
    # shortcut: clip fades are not applied here (a fade-out only makes the silence start earlier)
    tail = _quiet_s(audio[prev.source], rp.src_end, level_db(prev.gain), before=True)
    lead = _quiet_s(audio[nxt.source], rn.src_start, level_db(nxt.gain), before=False)
    silence = max(0.0, tail + (rn.out_start - rp.out_end) + lead)
    msg = (f"song change {prev.id} → {nxt.id} at {rn.out_start:.2f}s: {silence:.1f} s of audible "
           f"silence (below {SONG_GAP_DB:.0f} dBFS: {tail:.1f} s tail + {rn.out_start - rp.out_end:.1f} s "
           f"between the clips + {lead:.1f} s lead-in)")
    if silence > SONG_GAP_WARN_S:
        return [Issue(severity="warn", rule="song_change_gap", node=nxt.id,
                      message=msg + f": over {SONG_GAP_WARN_S} s reads as dead air. Unless a pause was "
                                    f"asked for, start the next song as the tail fades (skills/cutting/"
                                    f"references/song-sequence.md)")]
    return [Issue(severity="info", rule="song_change_gap", node=nxt.id, message=msg)]


def lint_plan(plan: Plan, maps: dict[str, MusicMap], segments: list[RenderSegment],
              splices: list[Splice], duration_s: Optional[float] = None,
              audio: Optional[dict[str, Audio]] = None) -> list[Issue]:
    issues: list[Issue] = []
    clips = {n.id: n for t in plan.tracks for n in t.clips if isinstance(n, ClipNode)}
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
        if _is_contiguous(prev, nxt, rp, rn, sp):
            continue
        if _is_song_change(rp, rn, maps):
            continue  # judged by song_change_gap below, not as a beat-matched join
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
        # mid_vocal: the cut lands in the middle of a sung phrase
        for side, node, t in (("outgoing", prev, rp.src_end), ("incoming", nxt, rn.src_start)):
            r = _mid_vocal(maps[node.source], t)
            if r:
                issues.append(Issue(
                    severity="warn", rule="mid_vocal", splice=sp.id, node=nxt.id,
                    message=f"{sp.id}: {side} cut at {t:.2f}s of source {node.source!r} falls inside "
                            f"a vocal range ({r[0]:.1f}-{r[1]:.1f}s), not at its edge"))
        # energy_drop
        smoothed = (sp.overlap_ms >= SMOOTHING_XFADE_MS or prev.fade_out is not None
                    or nxt.fade_in is not None)
        sa, sb = section(prev), section(nxt)
        if not smoothed and sa and sb:
            a, b = _edge_loudness(sa, True, rp.src_end), _edge_loudness(sb, False, rn.src_start)
            if a is not None and b is not None:
                drop = (a + level_db(prev.gain)) - (b + level_db(nxt.gain))
                if drop > ENERGY_DROP_DB:
                    issues.append(Issue(
                        severity="warn", rule="energy_drop", splice=sp.id, node=nxt.id,
                        message=f"{sp.id}: loudness drops {drop:.1f} dB ({prev.id} → {nxt.id}) "
                                f"with no fade or crossfade"))

    # song_change_gap: consecutive main-track clips (a gap node breaks the splice, not the change)
    main_segs = sorted((sg for sg in segments if sg.track == plan.tracks[0].id), key=lambda sg: sg.out_start)
    for rp, rn in zip(main_segs, main_segs[1:]):
        prev, nxt = clips.get(rp.node_id), clips.get(rn.node_id)
        if prev is not None and nxt is not None and _is_song_change(rp, rn, maps):
            issues += _song_change_gap(prev, nxt, rp, rn, audio)

    # ending: the last clip stops at a section end / the song's end, or has a fade_out
    main = [s for s in segments if s.track == plan.tracks[0].id]  # the cut ends where the main track does
    final = max(main, key=lambda s: s.out_end) if main else None
    if final:
        last = clips.get(final.node_id)
        if last is not None and last.fade_out is None:
            m, end = maps[last.source], final.src_end
            ends = [s.end for s in m.segments if s.end - s.start > 1e-3] + [m.duration]
            if not _near(end, ends):
                issues.append(Issue(
                    severity="warn", rule="ending", node=last.id,
                    message=f"the cut ends mid-section ({last.segment}#{last.index} at {end:.2f}s) "
                            f"with no fade_out"))

    # ending_drums: a fade over a section that is still driving
    if final:
        last = clips.get(final.node_id)
        m = maps[last.source] if last is not None else None
        ia = m.instrument_activity if m else None
        if last is not None and last.fade_out is not None and ia is not None and ia.drum is not None:
            end = final.src_end
            bar = bar_seconds(m.bars, m.beats, m.bpm, m.beats_per_bar)
            drums = segment_mean(ia.drum.values, ia.drum.hop_s, max(0.0, end - bar), end)
            if drums > DRUMS_BUSY:
                issues.append(Issue(
                    severity="warn", rule="ending_drums", node=last.id,
                    message=f"the cut fades out at {end:.2f}s of {last.source!r} while the drums are "
                            f"still busy (activity {drums:.2f} in the last bar): end on a drum break or "
                            f"a section edge instead of fading a groove"))

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
