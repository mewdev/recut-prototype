# Chicago — Edit Plan v12

## Changes from v11

### 1. other_ambient — REMOVED
- Even wet=0.12 room reverb adds a parallel copy that smears cello transients and shifts image
- The cello in the main piano/other.wav is already the blend — it sits naturally between drums and piano exit
- No additional layer needed

### 2. Drums: creative sweep-out on last 4 kicks (last bar before 2:29)
- Last bar: 209.13s abs (147.57s rel) → 210.90s (sweep_samp) = 1.765s = 4 beats
- Apply `filter_sweep(close, freq_ceil=8000, freq_floor=80, curve=1.0)` to this bar
- Apply `fade(1.0→0.0)` over the same bar
- Drums are fully silent at sweep_samp — zero overlap into the last phrase
- Effect: kicks "swoosh" from full → muffled as they fade — sounds intentional, not cut

### 3. piano_end: shorter fade-in (0.5s instead of 1.5s)
- No need for long crossfade since drums are already gone at sweep_samp
- 0.5s fade-in just softens the reverb onset (avoids abrupt room switch)

---

## Why v11 drums overlapped
Taper started AT sweep_samp and extended 1.5s INTO the last phrase.
Fix: process the last bar BEFORE sweep_samp → drums are silent when piano_end begins.

## Why other_ambient colored the cello
Parallel reverb copy at any wetness adds:
- Pre-delay coloration on transients
- Slight stereo image shift
- Phase smearing on attack
The cello's clarity is its natural attack. No copy needed.

---

## Signal path (v12 — simplified)
| Region | piano | bass | vox | drums |
|--------|-------|------|-----|-------|
| 0 → cut_rel (2:15) | full | full | full | full |
| cut_rel → last bar (2:15–2:27) | full | silent | silent | full |
| last bar (2:27–2:29) | full | silent | silent | sweep+fade → 0 |
| sweep_rel → end (2:29+) | sweep+reverb+fade | silent | silent | silent |

---

## Cumulative lessons
1. Segment label "chorus" = vocals enter → cut vocals before boundary
2. Sustained sources create reverb wash; transients (kick) create isolated blooms
3. Drums out BEFORE transition — process the last bar with sweep+fade, don't taper AFTER
4. Parallel reverb copy smears even at low wetness — remove if stem sounds colored
5. Transparent sweep: high freq_ceil + steep curve avoids spectral step
6. Never xfade_join time-aligned stems — additive mixing on single timeline
7. Drum bleed surfaces when signal fades → filter_sweep from transition start

---

## Key timestamps
| Event | Clip | Original |
|-------|------|---------|
| Start | 0:00 | 1:01.56 (61.56s) |
| Outro phrase A — full band | 2:01 | 3:02.56 (182.56s) |
| Bass + vox cut (cello plays clean) | 2:15 | 3:16.68 (196.68s) |
| **Last 4 kicks: sweep + fade begins** | **2:27.57** | **3:29.13 (209.13s)** |
| Piano exit starts (0.5s fade-in) | 2:29 | 3:30.90 (210.90s) |
| Fade-out starts | 2:44 | 3:45.56 (225.56s) |
| End | 2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v12.mp3`
