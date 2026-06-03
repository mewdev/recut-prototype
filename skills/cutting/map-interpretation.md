# Skill: Music Map Interpretation

The map tells you **structure**. It does not tell you **intent**. The gap between them is where all the editorial work happens.

---

## What to Trust

| Map field | Reliability | Use for |
|-----------|-------------|---------|
| `downbeats` | High | Cut points — always snap to nearest downbeat |
| `bpm` | High | Bar duration calculation: `bar = 60/bpm * beats_per_bar` |
| `segments[].start/end` | Medium | Coarse section boundaries — good for anticipating content changes |
| `segments[].label` | Medium | Content hints (see label guide below) |
| `beats` | High | Sub-bar precision for last-N-beats operations |
| `key`, `time_signature` | High | Harmonic context, but rarely needed for cuts |
| `chords` | Low-Medium | Useful for harmonic exit points, unreliable in complex passages |

---

## Segment Label Guide

| Label | What to anticipate |
|-------|-------------------|
| `chorus` | Vocals likely enter. Cut vocals **before** this boundary if making instrumental exit |
| `outro` | Repetitive material — loop or vamp. Good exit zone. May have multiple internal phrases |
| `intro` | Often instrumental. Safe re-entry point for a trimmed start |
| `verse` | Melodic content. Cutting mid-verse sounds wrong — wait for boundary |

---

## What the Map Misses

### Phrase-level subdivision
The map segments sections (8–32 bars). It does not mark phrase boundaries inside sections (4–8 bars). A 16-bar outro may be two 8-bar phrases (A + A-repeat) — only the user's ear can identify this.

**Implication:** when the user says "cut when it repeats again," they're describing a sub-segment boundary the map doesn't have.

### Repetition flag
No marker for "this segment is a literal repeat of the previous one." This is exactly what users hear as "it repeats too much" — but the map just gives two adjacent segments with the same label.

**Implication:** ask the user to identify the repetition point rather than guessing from structure alone.

### Per-stem content
The map describes the full mix. It does not tell you:
- Which instruments are active in each segment
- What's in each stem file (e.g., `other.wav` may contain cello + piano + misc)
- When vocals or specific instruments enter/exit within a section

**Implication:** always check stem energy (RMS) before assuming what's in a stem.

### Arrangement density curve
No per-instrument energy timeline. You cannot tell from the map alone when drums are driving vs when piano is carrying. Measure from stems.

---

## Practical Workflow

1. Read segments → identify the user's target zone (start/end/exit)
2. Snap to nearest downbeat in that zone
3. Check stem RMS in that zone before processing
4. Anticipate what enters at the next segment boundary (use label guide above)
5. Trust the user for sub-segment phrase boundaries — don't guess
