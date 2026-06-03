# Chicago — Edit Plan v9

## Core Realization
Reverb on isolated kick hits = isolated blooms, not ambience.
Sustained sources (piano) are what create a reverb wash.
Drums should stay dry and punchy throughout — that's their job.

## Changes from previous versions

### Structure
| Region | What plays |
|--------|-----------|
| 0:00 – 2:15 | Full band — all stems dry |
| **2:15 – 2:29** | Full band (drums stay!) + `other_ambient` fades in as preparation |
| **2:29 – 2:49** | Piano only → sweep + reverb + fade (clean exit) |

### Middle phrase (2:15–2:29): ambient preparation layer only
- `other_ambient` = `other.wav` → `reverb(wet=0.7, hall)` × 0.3
- Fades **in** over 2s at cut_samp (2:15), fades **out** over 1.5s ending at sweep_samp (2:29)
- Sits quietly underneath the full band — listener senses the space opening before drums leave
- Drums, bass, piano, vocals: untouched, full volume

### End phrase (2:29): drums taper out, piano sweep
- All stems except piano: 0.3s taper at sweep_samp
- Piano continues unbroken
- `filter_sweep` applied to piano from sweep_samp:
  - `freq_ceil=18000Hz` — starts near-transparent (no audible jump at 2:29)
  - `freq_floor=200Hz`
  - `curve=2.5` — stays near 18kHz for several seconds, then closes fast toward end
  - `duration=20.1s` (sweep_samp → CLIP_END_ABS)
- `reverb(wet=0.55, hall)` on piano from sweep_samp
- `fade(1.0→0.0)` on piano from sweep_samp

---

## Why freq_ceil=18000 fixes the 2:29 transition
At t=0 of the sweep: `freq = 18000 * (200/18000)^0 = 18000Hz` — inaudible filter.
With curve=2.5, the frequency stays above 10kHz for the first ~6s — well past any
perceptible boundary. Drums taper over 0.3s at exactly 2:29; by the time the filter
starts audibly closing, the listener has already accepted the piano-only texture.

---

## Cumulative lessons

1. Isolated transients (kick) don't reverb into ambient wash — need sustained sources
2. Transparent sweep start (high freq_ceil + steep curve) avoids spectral step at transition
3. Never xfade_join time-aligned stems — additive mixing on single timeline
4. Reverb on reverb = bloom — terminate ambient stems before they enter another chain
5. High-pass drums before reverb at ≥400Hz if reverb is needed at all

---

## Key timestamps
| Event | Clip | Original |
|-------|------|---------|
| Start | 0:00 | 1:01.56 (61.56s) |
| Outro phrase A (full band) | 2:01 | 3:02.56 (182.56s) |
| Phrase A repeat — full band + other_ambient fades in | 2:15 | 3:16.68 (196.68s) |
| Chorus — all stems taper, piano sweep begins | 2:29 | 3:30.90 (210.90s) |
| End | ~2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v9.mp3`
