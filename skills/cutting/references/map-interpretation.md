# Map Interpretation

The `MusicMap` (`src/recut/map/schema.py`) tells you **structure**. It does not tell you **intent**. Editorial judgment lives in that gap.

## Field-naming trap

`MusicMap.bars: list[float]` is a list of **downbeat timestamps** (bar starts, in seconds). `EnrichedSegment.bars: int` is a **bar count** for that segment. Same name, different shape and meaning — don't confuse a `Clip(bars=N)` request (a count) with the map's top-level `bars` array (timestamps).

## What to trust

| Map field | Reliability | Use for |
|---|---|---|
| `MusicMap.beats` / `MusicMap.bars` | High | Precise timestamps for cut points, sub-bar splicing via `offset_bars`/`offset_beats` |
| `MusicMap.bpm`, `beats_per_bar` | **Verify before trusting** | Nominal tempo: automation times (`"1 bar"`) and xfade/fade lengths in beats. Clip `bars`/`offset_bars` don't use it (they count the map's downbeats) — see below |
| `EnrichedSegment.start/end/duration` | Medium | Coarse section boundaries |
| `EnrichedSegment.segment_name` | Medium | Content hints (see label guide below) |
| `EnrichedSegment.downbeats` | High | Sub-bar precision, snap targets |
| `EnrichedSegment.phrases` | Medium | Sub-segment structure — the closest thing to a phrase boundary the map has |
| `EnrichedSegment.chords` | Low–Medium | Harmonic exit points; unreliable in dense/fast-changing passages |
| `EnrichedSegment.loudness_db` / `_start` / `_end` | High | Dynamics — where a section is loud/quiet, useful for exit and taper decisions |
| `MusicMap.key` (`tonic`, `mode`) | High | Harmonic context; rarely needed for structural cuts |

## Segment label guide (`SegmentName`)

`intro | verse | pre-chorus | chorus | bridge | inst | outro | silence | interlude | ending`

| Label | What to anticipate |
|---|---|
| `chorus` | Highest-energy, most memorable content — good clip target, watch vocal entries at its start |
| `outro` / `ending` | Often repetitive or already winding down — good exit zone |
| `intro` | Often instrumental — safe re-entry point for a trimmed start |
| `verse` | Melodic/narrative content — cutting mid-verse reads as wrong; wait for a boundary |
| `pre-chorus` / `bridge` | Transitional — good candidates for an `XFade` join point |
| `silence` | Literal gap — don't build a `Clip` around it expecting audio |

## What the map misses

- **Phrase-level detail below `phrases`**: `phrases` gives sub-segment timestamps, but nothing marks "this phrase is a literal repeat of the previous one." If the user says "cut when it repeats," that's still a judgment call between `phrases` entries — ask which repeat they mean if ambiguous.
- **Per-instrument activity only when enriched.** `instrument_activity` (drum/bass/vocal/other curves and `ranges`, from Demucs) and segment `drum_activity`/`vocal_activity` exist only when the map was enriched with stems; otherwise `loudness_db` is your only signal for "this section is dense/sparse". Use the `vocal` ranges to find sung/spoken phrases (e.g. a voice FX) and the `drum` ranges to find breaks.

## Clip bars count the map's downbeats; `bpm` is only the nominal tempo

A clip's `bars`/`offset_bars` (and `beats`/`offset_beats`) count the map's real downbeats
(beats), with fractions interpolated inside a bar: `offset_bars: 4` starts exactly on the
section's 5th downbeat even when the tempo drifts, and a section's whole bar count always fits
(`bars` equal to the section's `bars` ends on its end). Don't hand-compute fractional bars from
`bpm` to reach a downbeat; count downbeats instead.

`bpm` (nominal, one number) is still what automation times (`"1 bar"`, `"2 beats"`) and xfade
/fade lengths in beats use. On a track whose tempo drifts these can differ from the real bars
by a few percent; if `bpm` disagrees with the grid by a factor (an octave-wrong estimate), the
map is wrong: re-run the map rather than compensating in the plan.

## Practical workflow

1. Resolve the user's target zone from `segment_name` (+ `index` if a label repeats).
2. Verify `bpm` against the map's real bar spacing (above) before doing any bar/beat
   arithmetic — cheap, do it once per song, saves rework.
3. Use `offset_bars`/`offset_beats` + `bars`/`beats` to splice into the middle of a
   segment (e.g. only the second half of a chorus) — see the fp-boundary note above if
   the tail should run to the segment's natural end.
4. Check `loudness_db_start`/`loudness_db_end` of the next segment before deciding on a hard cut vs. a crossfade.
5. Trust the user for anything below phrase-level resolution — don't guess a sub-phrase repeat point.

## Segment boundaries are already snapped — `Clip` doesn't offer its own snap anymore

`make_map.py` snaps both `segment.start` and `segment.end` to the nearest downbeat at
map-generation time (`recut.map.helpers.snap_to_downbeat` — a different function from
the now-removed `Clip.snap_to_downbeat`, don't confuse the two). Every segment in a
freshly-generated map already starts and ends on a downbeat; there's no per-`Clip`
snapping to reach for anymore. (`Clip` used to have a `snap_to_downbeat` flag for this —
removed after repeated real-world use showed it was both redundant, given this
map-level snap, and actively harmful: it snapped a clip's *end* to `downbeats[-1]`, the
start of the segment's last bar rather than its actual end, silently dropping the final
bar whenever a segment's downbeat array didn't include a trailing marker flush with its
own end.)
