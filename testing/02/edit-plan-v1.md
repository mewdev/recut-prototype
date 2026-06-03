# Chicago — Edit Plan v1

## User Intent
> "potřebovaly bychom to zkrátit od 1:01, když se začne znovu opakovat ten motiv"
> ("We'd need to shorten it from 1:01, when the motif starts repeating again")

Trim the track at the point of repetition (~1:01), keeping only the first pass.

---

## Song Structure (from analysis)
| Start | End | Label |
|-------|-----|-------|
| 0:00 | 0:24 | verse |
| 0:24 | 0:38 | verse |
| 0:38 | 0:51 | chorus |
| **0:51** | **1:08** | outro ← user's "repeat starts" |
| 1:08 | 1:30 | intro (new section) |
| … | 3:55 | rest of song |

BPM: 136 · Key: C major · Time sig: 4/4

---

## Cut Decision

- **Keep:** 0:00 → 61.56s (downbeat at ~1:01:56, bar-aligned)
- **Remove:** 61.56s → end (173s of material)
- **Fade-out:** start at 58.0s (one bar before cut), 3.5s linear fade to silence
  - This lands the fade on the downbeat at 58.01s and completes just before 61.56s
  - Feels like a natural resolution rather than a hard chop

## Operations
1. `trim` — keep 0 → 61.56s
2. `fade_out` — 3.5s starting at 58.0s (overlapping the trim point)

## Output
- `testing/02/chicago-cut-v1.mp3`
- Original: 3:55 → Result: ~1:01 (61.5s)
