---
name: music-theory
description: Use this skill when a cutting decision needs real musical judgment, not just structural validity — which section is the strongest hook to keep in a short edit, whether a candidate cut point lands on a clean harmonic cadence or leaves things hanging, how energy/density should arc across a sequence of sections, where a natural phrase boundary falls inside a segment, or how to read the chord/key data in a song's MusicMap. It's the analytical companion to the `cutting` skill: `cutting` handles mechanics (Clip/XFade/compose/validate), this skill handles "is this choice musically good." Also usable standalone for structural/harmonic questions about an existing recording ("what's the hook here," "is this a good place to loop"). Do NOT use for composing new melodies, lyrics, or orchestration — that's `INSPO_music-composition`'s job (a large general composition-advisory skill kept only as reference material, not meant to be loaded for cutting work). Do NOT use for edit mechanics (node building, effects, rendering) — that's `cutting`'s job.
---

# Music Theory (for cutting)

Structural and harmonic judgment for evaluating and selecting sections of an **existing recording** — not for composing new material. Every file here is written from a detection/evaluation angle: given audio that already exists, recognize its structure and judge which choices serve it, rather than prescribing what to compose next.

## Why this exists

`skills/cutting/references/validation-workflow.md` is explicit that `validate()` only checks structural validity (does a segment exist, does a length fit) — it has no notion of whether a cut is *musically* good. This skill fills that gap: cadence quality at cut points, energy/density arcs across a sequence, phrase-level cut granularity, and hook identification.

## Core workflow

1. **Read `references/00-navigation.md` first** — routes your question to 1–3 files.
2. **Ground everything in the real map data.** This skill's judgment is only useful if applied to `MusicMap`/`EnrichedSegment` fields that actually exist (`segments[].chords`, `.loudness_db*`, `.phrases`, `.downbeats`) — see `skills/cutting/references/map-interpretation.md` for the field reference, and `assets/chord-notation.md` here for reading the map's chord format.
3. **Translate judgment into a `cutting`-skill action.** A conclusion like "this boundary is a half cadence, not a clean exit" should change a `Clip`/`XFade` choice (e.g. which `offset_bars`/`bars` value to land on, which `index` occurrence to use, whether to `XFade` instead of a hard cut) — this skill doesn't touch `Clip`/`XFade`/`compose()` itself.

## Navigation

```
references/
├── 00-navigation.md                ← Read this first
├── cut-points-and-cadences.md      ← Is this boundary a clean exit? Cadence types, tension/stability
├── song-form-and-sections.md       ← Section roles (intro/verse/chorus/...), mapped to recut's SegmentName
├── phrase-boundaries-and-groove.md ← Sub-segment cut granularity: phrase length, elision risk, beat/bar alignment
├── energy-arcs-and-density.md      ← How energy/density should arc across a sequence of cuts
└── hooks-and-highlights.md         ← Which section is the strongest keeper in a short edit

assets/
├── chord-notation.md               ← recut's ROOT:QUALITY chord format, translated to lead-sheet/Roman numeral
└── section-role-quickref.md        ← One table: section type × density × cadence risk × hook likelihood

scripts/
└── check_skill.py                  ← Maintainer check: SegmentName mentions + chord examples vs live recut vocab
```

## What this skill does NOT cover

- Writing new melodies, chord progressions, lyrics, or orchestration for material that doesn't exist yet — general composition is `INSPO_music-composition`'s domain (kept only as source material for this skill, not for direct use).
- Building `Clip`/`XFade` nodes, applying effects, validating, or rendering — that's `cutting`.
- Generating or enriching a `MusicMap` — that's `recut analyze`/`recut map`.

## Honesty about gaps

`MusicMap` has no genre field today, so genre-specific conventions (K-pop multi-hook structure, EDM drop/build/breakdown) can inform judgment only when the user names the genre explicitly — don't assume one. If a question needs theory this skill doesn't cover, say so rather than guessing.
