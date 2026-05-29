# Music Cutting System — Project Plan

## Core Idea

A system that understands music structurally and cuts audio files **meaningfully** — respecting harmony, phrase boundaries, cadences, and song structure. The mental model is **Remotion for audio** — code/data drives musical editing decisions instead of raw frame numbers or timestamps.

---

## Architecture

```
Audio file
    ↓
Analysis Pipeline
— multiple tools (librosa, Essentia, madmom, chord detectors)
— reconciliation layer (resolves conflicts between tools)
— outputs: unified JSON Music Map
  + candidate cut points (bar 16 is a cadence, section boundary at 1:24)
    ↓
General LLM (user-facing)
— receives: music map + candidate cuts + user intent in natural language
— outputs: selected cuts + creative framing
  ("use chorus entry at 1:24, fade over 2 beats for 30s ad version")
    ↓
Cutting Instruction Layer  ← compiler/validator
— translates LLM selection into precise executable primitives
— validates against the map (catches hallucinated timestamps)
— deterministic logic, no ML needed here
    ↓
Specialized Cutting Model
— trained on (map + instructions) → good cuts
— where musical taste lives
— trained on (map, instruction, good cut) triplets
    ↓
ffmpeg execution layer
    ↓
Output audio
```

---

## The JSON Music Map

The core artifact. An open, inspectable, portable representation of a song that every layer consumes.

Fields earned by use cases — nothing goes in without a primitive that needs it. Likely includes:

- Sections with labels (intro, verse, chorus, bridge, outro)
- Beat/bar positions with sample-accurate timestamps
- Chord progression with harmonic function labels
- Cadence types and positions (perfect, imperfect, plagal)
- Phrase boundaries
- Energy curve / arrangement density per section
- Key and tempo (including changes)
- Structural repetition map (which sections are harmonically equivalent)

**The moat is map quality** — coverage × accuracy × resolution. The reconciliation layer that combines multiple analysis tools is the hardest and most defensible technical piece.

---

## Cutting Primitives

Pure functions over the music map. Musical meaning, not raw timestamps.

**Tier 1 — Standard cuts:**
- `cutAtSectionBoundary(map, "chorus", 1)`
- `fadeAtCadence(map, timestamp)`
- `loopSection(map, "verse", 2)`
- `removeIntro(map)`
- `fadeOutAfterSection(map, "last_chorus")`

**Tier 2 — Non-linear joins:**
- `borrowEndingCadence(map, from="outro", to="chorus_2")`
- `crossfadeAtHarmonicNeutralPoint(map, section_a, section_b)`
- `removeBridgeCleanly(map)` — without energy drop feeling abrupt
- `extendByRepeat(map, section, n)` — seamless repeat

**Tier 3 — Creative/prompt-driven:**
- `makeRadioEdit(map, maxDuration="3:00")`
- `buildTensionBeforeDrop(map)`
- `endTooSoon(map)` — creative effect

---

## The Specialized Cutting Model

The piece that gives the system **taste**, not just correctness.

Trained on triplets:

```json
{
  "music_map": { "..." : "..." },
  "instruction": "end on chorus energy, 30 seconds",
  "correct_edit": {
    "type": "non_linear_join",
    "primitive": "borrow_ending_cadence",
    "from": { "section": "outro", "bar": 48, "beat": 1 },
    "to": { "section": "chorus_2", "bar": 32, "beat": 3 },
    "reason": "IV chord at bar 32 beat 3 provides clean resolution, energy curves match within 0.1",
    "crossfade_ms": 800
  }
}
```

Training data comes from documenting manual editing decisions — **every intervention is a future training example**. The `reason` field is the most important — it's where musical intelligence gets encoded.

---

## Use Case Bank — Immediate Next Step

Three tiers, collected before touching the schema:

| Tier | Type | Examples |
|------|------|---------|
| 1 | Standard cuts | 30/60s ad, remove intro, fade after chorus |
| 2 | Non-linear joins | Borrow ending cadence, bridge removal, seamless repeat |
| 3 | Creative/prompt | Radio edit, tension building, "ends too soon" |

**Capture format per case:**

```
ID:
Name:
Prompt:
Genre tested:
Information needed from audio:
Decision made:
Standard cut or non-linear join:
Manual intervention needed (why):
Result quality: 1-5
Notes:
```

The **"information needed from audio"** column directly becomes schema fields. Cases that break are the most valuable — document every failure.

---

## Remotion Integration — Second Step

After the core pipeline is solid, wrap it as a React/Remotion package.

**The shift in mental model:**

```jsx
// Standard Remotion — think in frames
<Sequence from={0} durationInFrames={90}>
  <Audio src="track.mp3" trimAfter={90} />
</Sequence>

// Music-aware Remotion — think in musical structure
<MusicSequence map={musicMap} section="chorus_1" trimTo="cadence">
  <Audio src="track.mp3" />
</MusicSequence>
```

**Component library:**

- `useMusicMap(src)` — core hook, fetches and exposes the map
- `<MusicSequence>` — section names instead of frame numbers
- `<MusicAudio>` — map-aware trimming and crossfading
- `<BeatSync>` — sync animations to beats and phrase boundaries
- `<SectionTransition>` — handles non-linear joins declaratively

**Distribution strategy:** open source the Remotion package, keep analysis pipeline proprietary/hosted. Open core wedge into the Remotion community — Jonny Burger (creator) is accessible, a well-built package could get featured in their resources list.

---

## Industries & Monetization

**Highest value targets:**

| Industry | Pain point | Value |
|----------|-----------|-------|
| Sync licensing (Artlist, Epidemic Sound) | Catalogue-scale versioning | High |
| Ad creative platforms | 15s/30s/60s cuts at scale | High |
| AI video generation (Sora, Runway) | Music-aware scene cuts | Growing fast |
| Podcast/video editors (Descript) | Clean music bed cuts | Medium |
| Game audio middleware (FMOD, Wwise) | Dynamic adaptive music | Medium |
| Social media tools (CapCut) | Harmonically correct auto-cuts | High volume |

**The moat:**
- Map quality (analysis pipeline accuracy)
- Primitive library (musical correctness of cuts)
- Training dataset of `(map, instruction, good cut)` triplets — not replicable quickly

**Monetization model:**
- API/infrastructure — send audio, get JSON map back, pricing per track or per minute
- Open core — open source schema + Remotion package, charge for hosted pipeline
- Vertical tool — pick one industry, build full UX on top

---

## Competitive Landscape

| Tool | What it does | Overlap | Gap |
|------|-------------|---------|-----|
| Remotion | React-based video rendering | Mental model only | No music structure awareness at all |
| WavTool | AI-powered DAW | Natural language editing UX | Black box, no open map, creation-focused not cutting-focused |
| Udio | AI music generation + inpainting | Section-level editing concept | Only works on Udio-generated audio, not arbitrary files |
| Moises | Stem separation, chord detection | Analysis layer | No cutting primitives, no LLM orchestration |

**The gap none of them fill:** an open, inspectable, portable music map that other tools can consume, with cutting as composable primitives and LLM orchestration on top.

---

## Build Sequence

```
Step 1 — Collect and document editing use cases        ← NOW
          stress test what the map needs to contain

Step 2 — Design JSON music map schema
          every field earned by a use case

Step 3 — Build analysis pipeline
          multi-tool reconciliation layer is the core moat

Step 4 — Build cutting primitive library
          pure functions over the map

Step 5 — LLM orchestration layer
          use cases as few-shot examples in prompts

Step 6 — Remotion integration
          useMusicMap hook → components → open source package

Step 7 — Specialized cutting model
          train on documented use case triplets
```

---

## Key Insight

The JSON map **decouples understanding from execution**.

- Analysis tools do the hearing
- LLM does the reasoning
- Specialized model has the taste
- ffmpeg does the cutting

Each layer stays in its competence zone and can be improved independently. The map is the contract between all of them.
