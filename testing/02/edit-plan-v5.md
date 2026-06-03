# Chicago — Edit Plan v5

## Changes from v4
1. **No xfade_join** — piano flows as a single continuous stream, never split
2. **Drums don't cut** — instead reverb-heavy (wet=0.85, hall) after phrase A repeat downbeat, creating an ambient ghost rather than a hard stop
3. Creative exit (sweep + reverb + fade) unchanged from v4

---

## Why v4 timing broke

`xfade_join` overlaps the tail of segment A with the head of segment B.
This consumed 300ms from the start of `piano_b`, shifting the phrase repeat 300ms early in the output. Simultaneously, two time-offset copies of piano played during the crossfade → phase smearing on the piano. The fix: never split a continuous stem. Build the mix additively on one shared timeline.

---

## Additive mixing strategy (v5)

All stems loaded for the **full clip duration** (61.56s → 231.0s). Timeline is never split.

| Track | 0 → 2:15 (cut_rel 135.12s) | 2:15 → end |
|-------|---------------------------|------------|
| piano | full, unmodified | full, unmodified |
| bass | full | faded out (0.3s taper at cut) → silent |
| vox | full | faded out (0.3s taper at cut) → silent |
| drums_dry | full | faded out (0.3s taper at cut) → silent |
| drums_reverb | silent (zeroed) | fades IN (0.3s) → wet=0.85 hall reverb |

**Sum at any point** = piano + bass + vox + drums_dry + drums_reverb

---

## Drum reverb treatment (phrase A repeat: 2:15 → 2:29)

- `reverb(drums_stem, wetness=0.85, reverb_type="hall")`
- This gives a spacious ghost: the rhythm is still faintly implied but sits far back in the room
- Creates distinction between phrase A (tight, punchy) and phrase A repeat (open, dissolving) without a hard cut

## Creative exit (2:29 / 210.90s abs → end)
Unchanged from v4:
- `filter_sweep(direction="close", freq_floor=200, freq_ceil=8000, duration=20s, curve=0.6)`
- `reverb(wetness=0.55, reverb_type="hall")`
- `fade(vol_start=1.0, vol_end=0.0)` over the full sweep section

---

## Key timestamps

| Event | Clip time | Original time |
|-------|-----------|--------------|
| New start | 0:00 | 1:01.56 (61.56s) |
| Outro — phrase A (full band) | 2:01 | 3:02.56 (182.56s) |
| **Phrase A repeat — drums reverb** | **2:15** | **3:16.68 (196.68s)** |
| Chorus — sweep + reverb begins | 2:29 | 3:30.90 (210.90s) |
| End | ~2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v5.mp3`
