# Chicago — Edit Plan v10

## Single change from v9
Move `vox` taper from sweep_samp (2:29) → cut_samp (2:15).

## Why
| Time | vox rms | vox peak |
|------|---------|---------|
| 2:15–2:27 | ~0.0002 | ~0.003 |
| **2:28** | **0.062** | **0.289** |
| **2:29** | **0.103** | **0.361** |
| 2:31 | 0.004 | 0.051 |

A chorus vocal phrase enters at **2:28**, one full second before the sweep_samp taper began.
The vocal hit full volume before the 0.3s taper could silence it.

## What the map told us
Segment label `"chorus"` at 3:30.44 (= 2:29 clip) signals strong vocal entry at that boundary.
Lesson: use segment labels to **anticipate** what enters, not just describe structure.
Vocals should always be cut before a "chorus" boundary if the intention is an instrumental exit.

## Signal path (v10)
| Region | piano | bass | vox | drums | other_ambient |
|--------|-------|------|-----|-------|---------------|
| 0 → cut_rel (2:15) | full | full | full | full | silent |
| cut_rel → sweep_rel (2:15–2:29) | full | **silent** | **silent** | full | fades in |
| sweep_rel → end (2:29+) | sweep+reverb+fade | silent | silent | silent | silent |

## Cumulative lessons
1. Use segment labels to anticipate what enters at boundaries (chorus → expect vocals)
2. Taper any stem **before** its next entry point, not at it
3. Sustained sources (piano) create reverb wash; isolated transients (kick) don't
4. Transparent sweep start (high freq_ceil + steep curve) avoids spectral step at transition
5. Never xfade_join time-aligned stems — additive mixing on single timeline
6. Reverb on reverb = bloom — terminate ambient stems before second reverb chain

## Key timestamps (unchanged from v9)
| Event | Clip | Original |
|-------|------|---------|
| Start | 0:00 | 1:01.56 (61.56s) |
| Outro phrase A (full band) | 2:01 | 3:02.56 (182.56s) |
| Bass + vox cut, other_ambient fades in | 2:15 | 3:16.68 (196.68s) |
| Drums taper, piano sweep begins | 2:29 | 3:30.90 (210.90s) |
| End | ~2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v10.mp3`
