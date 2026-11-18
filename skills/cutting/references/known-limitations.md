# Known Limitations

recut is an early prototype (see repo `CLAUDE.md`). Say these gaps out loud when relevant rather than silently working around them.

## Layers, not a mixer

Tracks (PLAN §3.2) all start at 0 s; a track that begins with a `gap` places a layer later.
Each track has its own devices, volume, pan and automation, and every track can send to the
returns. There is no sidechain/ducking between tracks and no time-stretching, so layering two
*songs* (a full mashup) still needs compatible tempos and sections chosen by hand.

## Stems are separated after the fact

A stem source (`stems/<source>/<stem>.flac`, with the song's map) exists when the analysis kept
the stems (the default; older tickets: `recut ticket enrich <id> --force`). Demucs htdemucs separation has bleed and
artefacts: fine for a short voice hit or a drum loop, audible on long exposed parts (STATUS M7).
Clips are otherwise full mixes and every device acts on what the clip contains.

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
