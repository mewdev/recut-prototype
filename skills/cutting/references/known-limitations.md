# Known Limitations

recut is an early prototype (see repo `CLAUDE.md`). Say these gaps out loud when relevant rather than silently working around them.

## No `eq` primitive

Only `cut`, `fade`, `filter_sweep`, `reverb`, `delay`, `xfade`, `chain` exist. A static (non-swept) filter is available via `FilterSweep(freq_start=freq_end=cutoff)` — see `effects-routing.md`. There's no dedicated static-EQ primitive or effect.

## No partial-clip effect application

Every `Effect` applies to the *entire* buffer a `Clip` cuts — there's no way to say
"apply this only to the last N bars, leave the rest of the clip untouched." `Fade`'s
envelope always spans the whole clip; `Reverb`/`Delay` have no offset/duration concept
at all; `FilterSweep`'s `duration` param looks like it should give this but doesn't —
it **truncates** the clip to `duration` rather than sweeping then holding at `freq_end`
for the remainder (tested: 4.0s input, `duration=1.0` → 1.0s output, not 4.0s).

**Current workaround:** split into two `Clip()` calls
on the same `segment_name`/`index` — one dry with `bars=N`, one effected with
`offset_bars=N` and no `bars` cap. Real cost, not just verbosity: the complementary
`offset_bars`/`bars` arithmetic is exactly what produces the fp-boundary trap (`offset_bars
+ bars` summing to precisely `segment.end`, tripped by the map's own bar-grid jitter) hit
repeatedly this session. See issue [#53](https://github.com/mewdev/recut-prototype/issues/53).

## No live per-instrument/stem editing

`compose(music_map, audio, *nodes)` takes exactly one `Audio` — the full mix. `Clip.source` and `Composition.sources` (`src/recut/project.py`) exist as dataclass fields but are **not read anywhere at render time** — they're placeholders for a future multi-source/stem path, not a working feature. Do not tell a user "I'll isolate the drums and fade just those" — that call doesn't exist. All effects apply to the whole mix (`effects-routing.md`, `transitions-and-masking.md`).

## Thin test coverage on primitives

`tests/primitives/test_primitives.py` covers `cut`, `fade`, `chain`, `xfade`, and `Clip` fx/loop application. `filter_sweep`, `reverb`, and `delay` have no dedicated unit tests as of this writing. `compose()` itself has no direct test suite — it's exercised indirectly through the `Clip` fx/loop tests.

## Validator is 3 rules, not a musical linter

See `validation-workflow.md` — `label_exists`, `duration_exceeds`, `sequence_boundaries` only. No key/energy/rhythm-aware checks exist yet.

## No map generation or DAW/notation concerns here

This skill doesn't cover building/enriching a `MusicMap` (`recut analyze`/`recut map`, `src/recut/map/make_map.py`) or pure music-theory questions (`music-composition` skill) — those are explicitly out of scope, see `SKILL.md`.
