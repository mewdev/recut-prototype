---
name: cutting
description: Use this skill when the user wants an audio edit or cut built through the recut framework — trimming a track, building a shorter or radio edit, looping a section, crossfading between sections, giving a song an ending/exit, assembling a composition from a music map's segments (intro/verse/chorus/etc), or building an ambient/generative soundscape from song fragments (Fripp/Eno-style tape loops, "dreamy soundscape", "seamless ambient loop"). Triggers include direct edit requests ("shorten this to 90 seconds", "cut a radio edit", "loop the chorus twice", "make this fade out cleanly", "build a version that goes intro → verse → chorus", "turn this into an ambient loop") and requests to validate or render an existing composition. For musically creative decisions within a cut (which section is the strongest hook, whether a cut point lands on a clean cadence, how energy should arc across a sequence), pair with the `music-theory` skill. Do NOT use for composing new melodies/lyrics/orchestration (out of scope), or for generating or enriching a music map (`recut analyze` / `recut map` — analysis pipeline, not this skill).
---

# Cutting

Builds and renders audio edits against a song's `MusicMap` by writing a **plan**: `plan.json` (format v2, `docs/PLAN.md` §3.2), which reads like a small Ableton arrangement. This skill is about *executing* a cut correctly and musically — not music theory, not map generation.

## The model in 60 seconds

- A **track** holds **clips**. Each clip is chosen musically from the map (`segment` + `index`, optional `bars`/`beats`, `offset_bars`, `loop`) — never by free timecodes. Clips can come from several **sources** (several songs, or versions of one).
- A clip has **`gain`** (dB) and **fade handles** (`fade_in`/`fade_out`: `{length, shape}`).
- **`xfade`** nodes between clips join them: `length` + `shape`, or `out_shape`/`in_shape` per side. `"hold"` keeps a side at full level for the whole overlap.
- **Devices** (Ableton names: `utility`, `eq`, `auto_filter`, `reverb`, `delay`, `limiter`) sit on a clip, a track or the master.
- **Sends** (`sends: {"A": -6}`) feed **return tracks**, where reverb and delay live. A return keeps ringing after the clips that feed it end, so tails are never cut off.
- **Automation** moves a value over time: a ramp (`from`, `to`, `over`, `at`) or `points`, on `gain`, `sends.<return id>` or `devices.<id>.<param>`.
- **Units**: time is a string (`"1/8."`, `"2 bars"`, `"30ms"`); levels are dB or `"-inf"`; percentages are 0–100; frequencies are Hz; shapes are `linear`, `equal_power`, `exp`, `log`, `hold`. Full table: `assets/effects-cheatsheet.md`.

A minimal plan:

```json
{
  "version": 2,
  "sources": {"a": {"file": "inputs/a.mp3", "map": "maps/a.json"}},
  "returns": [{"id": "A", "name": "Reverb", "devices": [
    {"id": "verb", "type": "reverb", "decay": "3s", "dry_wet": 100}]}],
  "tracks": [{"id": "main", "clips": [
    {"id": "n1", "type": "clip", "source": "a", "segment": "intro", "index": 1,
     "fade_in": {"length": "1 beat", "shape": "linear"}},
    {"id": "n2", "type": "clip", "source": "a", "segment": "chorus", "index": 1, "bars": 8},
    {"id": "x1", "type": "xfade", "length": "2 beats", "shape": "equal_power"},
    {"id": "n3", "type": "clip", "source": "a", "segment": "inst", "index": 1, "offset_bars": 4,
     "sends": {"A": -6}, "fade_out": {"length": "2 bars", "shape": "exp"}}
  ]}],
  "target_duration_s": 60
}
```

Render with `recut ticket render <id>` (it prints the issues) or in code: `render_plan(Plan.model_validate(plan_dict), base_dir)` from `recut.engine`, which returns `(Audio, RenderInfo)`. Unknown fields are errors; the error messages name the section list or the bad unit, so read them.

## Core workflow

1. **Disambiguate the request first.** Most cutting prompts are underspecified — see `references/prompt-disambiguation.md`. State your interpretation explicitly before building anything.
2. **Read the map, don't guess.** Load the song's `MusicMap` and check `references/map-interpretation.md` for what each field does and does not tell you.
3. **Write the plan**: sources, one track of clips and `xfade`s, in order. Pick sections and lengths in bars.
4. **Render and read the issues.** `recut ticket render <id>` reports structure problems (`structure`), cross-song joins, `xfade_clamped`, `peak_clip`, and duration misses. See `references/validation-workflow.md` for what the checks cover and, importantly, what they don't.
5. **Apply effects with real signal-processing judgment** — see `references/effects-routing.md` and `references/transitions-and-masking.md` before adding devices, sends or automation. Reverb and delay belong on **returns** (a send), not inserted on every clip.
6. **Design the exit deliberately** if the cut needs an ending — see `references/exit-design.md`. If the song's real ending should land mid-song (the most common manual fix), use the **ending transplant** recipe: `references/ending-transplant.md` (three variants as `plan.json` snippets).
7. **Listen, then iterate.** `recut ticket iterate <id>` starts a new attempt instead of overwriting the last.

## Navigation

Always start with `references/00-navigation.md` — it routes a request to the 1–3 reference files you actually need. Don't load everything; if a request seems to need 5+ files, narrow the question first.

For hook selection, cadence-quality cut points, or energy-arc sequencing — musical judgment beyond structural validity — load the sibling `music-theory` skill alongside this one.

## Top-level structure

```
references/
├── 00-navigation.md            ← Read this first, every time
├── effects-routing.md          ← Which device/send/automation for which situation, chain ordering
├── ending-transplant.md        ← The song's real ending placed mid-song: 3 variants as plan.json
├── exit-design.md              ← How to end a cut deliberately
├── transitions-and-masking.md  ← Why cuts click, stagger rules, taper timing
├── map-interpretation.md       ← What the MusicMap tells you, what it doesn't, and a field-naming trap
├── prompt-disambiguation.md    ← Resolving vague cutting requests before touching anything
├── validation-workflow.md      ← What the checks catch, and what they do NOT catch
├── ambient-soundscapes.md      ← Generative/drone pieces from song fragments (Fripp/Eno style)
├── known-limitations.md        ← Honest gaps in the current recut implementation
└── api-reference.md            ← LEGACY Python API (Clip/XFade/Fade/Reverb/compose()); old saved compositions still load

assets/
└── effects-cheatsheet.md       ← Units, shapes, devices and their parameters, reverb decay table, delay sync values

scripts/
└── check_skill.py              ← Maintainer drift check: legacy API doc signatures vs live src/recut
```

## Honesty about gaps

recut is an early prototype. If a request needs something the framework can't do yet (per-instrument/stem editing, time-stretching to match tempos, more than one track, automatic key/energy-aware validation), say so explicitly and point at `references/known-limitations.md` rather than faking it with an unsupported field.

## Legacy Python API

The older `Clip`/`XFade`/`Fade`/`Reverb`/`Delay`/`FilterSweep` classes and `compose()` still work and are documented in `references/api-reference.md`, but they are deprecated. Saved compositions in that format load into a v2 plan through `recut.legacy.composition_to_plan`. Write new work as a plan.
