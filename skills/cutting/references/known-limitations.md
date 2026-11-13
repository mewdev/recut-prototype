# Known Limitations

recut is an early prototype (see repo `CLAUDE.md`). Say these gaps out loud when relevant rather than silently working around them.

## One track only

The engine renders exactly one track of clips, plus return tracks and the master. More than one track raises `multi-track not supported yet`. Layering (mashups, a vocal over another song's instrumental) is week-2 work; sequencing several sources (a medley, several versions of one song) works today.

## No stem or per-instrument editing

Clips are full mixes (clients send full mixes only). Every device acts on the whole mix: you can filter or duck "the mix", not "the drums". Do not tell a user "I'll isolate the drums and fade just those"; that doesn't exist. See `effects-routing.md`, `transitions-and-masking.md`.

## No time-stretching

Joins between songs with different tempos must be chosen to be compatible (breakdowns, outros, longer crossfades). `bpm_gap` warns when the tempos differ by more than about 3%; the engine will not match them for you.

## Reverb is approximate

`reverb` runs on pedalboard's Freeverb, which has no decay-time setting. `decay` is mapped to its room size through a measured table (0.53 s to 9.5 s), `size` only scales that, and there is no early-reflection control. It sounds like a plain algorithmic room; don't promise a specific RT60 or a convolution hall.

## Automation covers a fixed set of parameters

Automation can move `gain`, `sends.<id>` and these device parameters: `utility` gain/width, `eq` low_cut/high_cut, `auto_filter` frequency/resonance, `reverb` dry_wet/hi_cut, `delay` dry_wet/feedback/filter_lo/filter_hi. `decay`, `time`, `size`, EQ bands and pan can't be automated; the error message lists what can.

## Validator is a few structure rules plus cross-song checks, not a musical linter

See `validation-workflow.md`. No energy- or rhythm-aware checks beyond the beat-grid join checks.

## No map generation or DAW/notation concerns here

This skill doesn't cover building/enriching a `MusicMap` (`recut analyze`/`recut map`, `src/recut/map/make_map.py`) or musical-judgment questions (`music-theory` skill) — those are explicitly out of scope, see `SKILL.md`.

## Legacy Python API gaps (deprecated API only)

`compose()` takes one source, applies each clip's `fx` to the whole clip, truncates `FilterSweep(duration=...)` to its duration, and has no EQ or sends. All of that is fixed in plan v2; old compositions convert through `recut.legacy`.
