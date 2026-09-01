# Phrase Boundaries and Groove

Where inside a segment a cut actually lands clean — sub-segment granularity that `EnrichedSegment.start`/`.end`/`.downbeats` alone don't capture. Use `EnrichedSegment.phrases` (`src/recut/map/schema.py`) as the closest thing the map gives you to phrase-level timestamps.

## Phrase length is genre-dependent — don't assume 4 bars

| Context | Default phrase length |
|---|---|
| Pop/rock verse | 4 bars (two phrases = 8-bar half-section) |
| Pop/rock chorus | 4 or 8 bars |
| Jazz standard | 8 bars |
| Hip-hop verse | 16 bars ("a 16"), often subdivided 4×4 |
| EDM | 16 or 32 bars, defined by structural change rather than phrase grammar |
| K-pop pre-chorus/chorus/post-chorus | 4+4, 8, 4 respectively (mixed) |

A phrase ends with some kind of cadential closure (see `cut-points-and-cadences.md`) — it's the musical equivalent of a breath. **Prefer cutting at a `phrases` timestamp over an arbitrary point inside a segment**; that's where the music itself pauses.

## Phrase elision — a real cut risk

When one phrase's cadence coincides with the next phrase's start (no gap), cutting exactly at that `phrases` boundary can still sound wrong — there was never a breath there to cut at. This is more common in through-composed and heavily syncopated material, less common in pop (which tends to leave clear vocal-breath gaps between phrases). If a candidate `phrases` boundary doesn't correspond to an actual drop in `loudness_db`, treat it as a possible elision and look at the neighboring boundary instead.

## Cut on beat/bar boundaries, respect the groove pattern

Even within a phrase, an arbitrary sample-accurate cut point can land mid-groove-pattern (e.g., splitting a ghost-note fill, or landing between a kick and its paired snare in a syncopated pattern) and read as wrong even when harmonically fine. Prefer `Clip(snap_to_downbeat=True)` or an explicit `bars`/`beats` offset over a raw timestamp — recut's `bars_to_seconds`/`beats_to_seconds` (`src/recut/map/parser.py`) exist precisely so cuts land on the beat grid rather than an arbitrary point.

## Feel changes — check before assuming groove continuity

A song can shift between full-time and half-time feel internally (same BPM, but the snare moves from beats 2-and-4 every bar to beat 3 only every other bar — common in modern rock/pop choruses and in trap). A cut that straddles a feel change can glue two halves that don't actually share a groove, even at the identical tempo. There's no dedicated map field for this — if a cut spans a large loudness/density jump at a chorus/bridge boundary, treat a feel change as a real possibility and prefer cutting exactly at the segment boundary rather than mid-segment across it.

## Quick reference

| Need to... | Do |
|---|---|
| Cut mid-segment at a natural breath | Use the nearest `EnrichedSegment.phrases` timestamp, snapped to the beat grid |
| Avoid an elision trap | Cross-check the `phrases` boundary against a real `loudness_db` dip before trusting it |
| Avoid splitting a groove pattern | Snap to `downbeats`, not an arbitrary sample offset |
| Avoid gluing mismatched feels | Cut at the segment boundary, not across a suspected feel change |
