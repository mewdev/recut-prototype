---
name: cutting
description: Use this skill when the user wants an audio edit or cut built through the recut framework — trimming a track, building a shorter or radio edit, looping a section, crossfading between sections, giving a song an ending/exit, assembling a composition from a music map's segments (intro/verse/chorus/etc), or building an ambient/generative soundscape from song fragments (Fripp/Eno-style tape loops, "dreamy soundscape", "seamless ambient loop"). Triggers include direct edit requests ("shorten this to 90 seconds", "cut a radio edit", "loop the chorus twice", "make this fade out cleanly", "build a version that goes intro → verse → chorus", "turn this into an ambient loop") and requests to validate or render an existing composition. For musically creative decisions within a cut (which section is the strongest hook, whether a cut point lands on a clean cadence, how energy should arc across a sequence), pair with the `music-theory` skill. Do NOT use for composing new melodies/lyrics/orchestration (that's `INSPO_music-composition`, kept only as reference material), for generating or enriching a music map (`recut analyze` / `recut map` — analysis pipeline, not this skill), or for the `ui/` frontend editor.
---

# Cutting

Builds and renders audio edits against a song's `MusicMap` using the recut compositor (`Clip`/`XFade` nodes, `compose()`, `validate()`). This skill is about *executing* a cut correctly and musically — not music theory, not map generation.

## Core workflow

1. **Disambiguate the request first.** Most cutting prompts are underspecified — see `references/prompt-disambiguation.md`. State your interpretation explicitly before building anything.
2. **Read the map, don't guess.** Load the song's `MusicMap` and check `references/map-interpretation.md` for what each field does and does not tell you.
3. **Build the composition** as a sequence of `Clip`/`XFade` nodes — see `references/api-reference.md` for exact signatures.
4. **Validate before rendering.** Always call `validate(music_map, *nodes)` — see `references/validation-workflow.md` for what it catches and, importantly, what it doesn't.
5. **Apply effects with real signal-processing judgment** — see `references/effects-routing.md` and `references/transitions-and-masking.md` before adding `Reverb`/`FilterSweep`/`Delay`.
6. **Design the exit deliberately** if the cut needs an ending — see `references/exit-design.md`.
7. **Render.** `recut validate <name>` then `recut render <name>` (see `references/api-reference.md` for the CLI).

## Navigation

Always start with `references/00-navigation.md` — it routes a request to the 1–3 reference files you actually need. Don't load everything; if a request seems to need 5+ files, narrow the question first.

For hook selection, cadence-quality cut points, or energy-arc sequencing — musical judgment beyond structural validity — load the sibling `music-theory` skill alongside this one.

## Top-level structure

```
references/
├── 00-navigation.md            ← Read this first, every time
├── api-reference.md            ← Ground truth: exact current signatures for primitives, Clip/XFade, Effect, compose(), validate(), map helpers, and the CLI
├── map-interpretation.md       ← What the MusicMap tells you, what it doesn't, and a field-naming trap
├── prompt-disambiguation.md    ← Resolving vague cutting requests before touching anything
├── effects-routing.md          ← Which effect for which situation, correct chain ordering, known gaps (no eq primitive)
├── transitions-and-masking.md  ← Why cuts click, stagger rules, taper timing
├── exit-design.md              ← How to end a cut deliberately
├── validation-workflow.md      ← When/why to call validate(), and what it does NOT catch
├── ambient-soundscapes.md      ← Building generative/drone pieces from song fragments (Fripp/Eno style) — different arrangement pattern from editing a song's structure
└── known-limitations.md        ← Honest gaps in the current recut implementation

assets/
└── effects-cheatsheet.md       ← Quick-lookup reverb presets, filter_sweep curve behavior, xfade curves

scripts/
└── check_skill.py              ← Maintainer drift check: doc code samples vs live src/recut signatures
```

## Honesty about gaps

recut is an early prototype. If a request needs something the framework can't do yet (per-instrument/stem editing, an `eq` primitive, automatic key/energy-aware validation), say so explicitly and point at `references/known-limitations.md` rather than faking it with an unsupported call.
