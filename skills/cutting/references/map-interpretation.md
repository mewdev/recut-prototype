# Map Interpretation

The `MusicMap` (`src/recut/map/schema.py`) tells you **structure**. It does not tell you **intent**. Editorial judgment lives in that gap.

## Field-naming trap

`MusicMap.bars: list[float]` is a list of **downbeat timestamps** (bar starts, in seconds). `EnrichedSegment.bars: int` is a **bar count** for that segment. Same name, different shape and meaning — don't confuse a `Clip(bars=N)` request (a count) with the map's top-level `bars` array (timestamps).

## What to trust

| Map field | Reliability | Use for |
|---|---|---|
| `MusicMap.beats` / `MusicMap.bars` | High | Precise timestamps for cut points — `Clip(snap_to_downbeat=True)` uses `segment.downbeats` |
| `MusicMap.bpm`, `beats_per_bar` | **Verify before trusting** | `bars_to_seconds()` / `beats_to_seconds()` for `Clip(bars=...)`/`Clip(beats=...)` — see verification step below |
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
| `intro` | Often instrumental — safe re-entry point for a trimmed start; also often the segment where a pickup/upbeat runs slightly before `segment.start`, which is exactly what `snap_to_downbeat=True` corrects for |
| `verse` | Melodic/narrative content — cutting mid-verse reads as wrong; wait for a boundary |
| `pre-chorus` / `bridge` | Transitional — good candidates for an `XFade` join point |
| `silence` | Literal gap — don't build a `Clip` around it expecting audio |

## What the map misses

- **Phrase-level detail below `phrases`**: `phrases` gives sub-segment timestamps, but nothing marks "this phrase is a literal repeat of the previous one." If the user says "cut when it repeats," that's still a judgment call between `phrases` entries — ask which repeat they mean if ambiguous.
- **No per-instrument/stem activity.** The map describes the full mix. It cannot tell you which instrument is carrying a section, or when a specific instrument enters/exits within it — see `known-limitations.md`. `loudness_db` is your only quantitative signal for "this section is dense/sparse."

## Verify `bpm` before using `bars=`/`beats=`/`offset_bars=`

`bars_to_seconds()`/`beats_to_seconds()` (`src/recut/map/parser.py`) compute purely
from the `bpm` field — they never look at the map's own `bars`/`beats` timestamp
arrays. If `bpm` is a stale or octave-wrong estimate (a real, apparently common
analysis-pipeline failure mode — found on a real song's map, where `bpm` was exactly
half the tempo implied by the song's own downbeat grid), every `bars=`/`beats=`/
`offset_bars=` value silently resolves to the wrong number of real seconds, with no
error — `validate()` still passes, `compose()` still runs, it's just wrong.

**Before trusting any `bars=`/`beats=`/`offset_bars=` value on a song you haven't
worked with before**, do this cheap check once:

```python
from recut.map.parser import bars_to_seconds
real_bar_spacing = music_map.bars[1] - music_map.bars[0]
print(bars_to_seconds(music_map, 1), "vs", real_bar_spacing)  # should match closely
```

If they disagree, the bpm field is wrong — either fix it at the source (derive a
corrected value from `music_map.bars`, e.g. the mean bar-to-bar spacing, and patch the
map JSON — cheap, gitignored, reversible) or account for the ratio in every
`bars=`/`beats=` value you write, which is much more error-prone and not recommended.

## `bars=`/`offset_bars=` summing to exactly a segment's end can false-positive an error

When a clip is split for a partial-effect application (dry portion + effected tail —
see `known-limitations.md`'s "No partial-clip effect application"), it's tempting to
give the second `Clip` an explicit `bars=` that makes `offset_bars + bars` land exactly
on `segment.end`. Don't — the real downbeat grid has a few ms of jitter per bar (beat
detection isn't perfectly uniform), so `bars_to_seconds()`'s bpm-derived arithmetic can
overshoot the segment's *actual* duration by single-digit milliseconds even when the
bar-count math looks exact on paper, tripping `validate()`'s strict `>` check
(`check_duration_exceeds`) with a confusing "N bars exceeds segment duration" error
where N bars visually *should* fit. **Fix: drop the `bars=`/`beats=` cap on the tail
clip and let it run to the segment's natural end instead of computing a value meant to
land exactly there.**

## Practical workflow

1. Resolve the user's target zone from `segment_name` (+ `index` if a label repeats).
2. Verify `bpm` against the map's real bar spacing (above) before doing any bar/beat
   arithmetic — cheap, do it once per song, saves rework.
3. Decide `snap_to_downbeat`. It snaps **both** ends to the downbeat grid
   (`downbeats[0]`/`downbeats[-1]`), not just the start — `downbeats[-1]` is the last
   *bar's start*, not `segment.end`, so if a segment's downbeat array doesn't include a
   trailing marker flush with its own end (common), `snap_to_downbeat=True` silently
   drops the segment's final bar. Check `segment.end - segment.downbeats[-1]` before
   using it on a segment you need the tail of — if that's ~1 bar, it will get cut. Also
   pointless (not just risky) whenever `segment.start` already equals `downbeats[0]`,
   which is common — verify before reaching for it out of habit, don't default to
   `True` for every intro/outro.
4. Use `offset_bars`/`offset_beats` + `bars`/`beats` to splice into the middle of a
   segment (e.g. only the second half of a chorus) — see the fp-boundary note above if
   the tail should run to the segment's natural end.
5. Check `loudness_db_start`/`loudness_db_end` of the next segment before deciding on a hard cut vs. a crossfade.
6. Trust the user for anything below phrase-level resolution — don't guess a sub-phrase repeat point.
