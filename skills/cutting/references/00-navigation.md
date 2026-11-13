# Navigation Map

Read this before anything else, every time. Find the row matching the request, load only the listed file(s).

## By topic

| User asks about | File(s) |
|---|---|
| Plan format, units, devices and their parameters, shapes, reverb decay table | `../assets/effects-cheatsheet.md`, `docs/PLAN.md` §3.2 |
| The song's real ending placed mid-song (ending transplant, "hit on top", reverb wash) | `ending-transplant.md` |
| LEGACY Python API: `Clip`/`XFade`/`Effect` fields, `compose()`/`validate()`, the old CLI | `api-reference.md` |
| "From X" / "make it shorter" / "creative ending" / any vague or underspecified cut request | `prompt-disambiguation.md` |
| What a `MusicMap` field means, how reliable it is, what it doesn't tell you | `map-interpretation.md` |
| Which device (reverb/delay/eq/auto_filter/utility), send or automation to use, ordering | `effects-routing.md` |
| Clicks, clipping, "why does this sound bad at the cut point", stagger/taper timing | `transitions-and-masking.md` |
| How to end a track, fade timing, exit types | `exit-design.md` |
| Whether to trust `validate()`, what it catches vs. what it silently allows | `validation-workflow.md` |
| "Can recut do X" / stem separation / eq / test coverage | `known-limitations.md` |
| Ambient/generative soundscape from song fragments, "Fripp/Eno style", "tape loop", "dreamy soundscape" | `ambient-soundscapes.md` |
| Quick unit/param lookup without reading a full reference | `../assets/effects-cheatsheet.md` |
| Which section is the strongest hook, is this a clean cadence, how should energy arc across the cut | sibling `music-theory` skill — not covered here |

## Rule

Load 1–3 files per request. If a request seems to need 5+, it's too broad — pick the dominant aspect, answer that, and offer to continue.

## Typical order for a full "build me a cut" request

1. `prompt-disambiguation.md` — resolve intent
2. `map-interpretation.md` — read the map correctly
3. `../assets/effects-cheatsheet.md` — write the plan (clips, `xfade`s, units)
4. `validation-workflow.md` — validate before rendering
5. `effects-routing.md` + `exit-design.md` (+ `ending-transplant.md`) — only if the cut needs effects or a designed ending

## Typical order for an ambient/soundscape request

Different shape — `ambient-soundscapes.md` alone covers most of it (source selection,
the single-clip `loop` pattern, effect recipe, verification checklist); pull in
`effects-routing.md` for the `Delay`/`Reverb` parameter detail it references, and
`known-limitations.md` if reprocessing an already-rendered mix comes up.
