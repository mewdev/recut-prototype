# Chicago — Edit Plan v2

## User Intent
> "Start from cca 1:01 till the end. End has repetitive motif/loop where is a space for some creative end."

Keep from ~1:01 to end. The final outro loop (3:43–3:55) is repetitive — use it as a canvas for a creative exit rather than a hard stop.

---

## Song Structure (full)
| Start | End | Label |
|-------|-----|-------|
| 0:00 | 0:24 | verse |
| 0:24 | 0:38 | verse |
| 0:38 | 0:51 | chorus |
| 0:51 | 1:08 | outro |
| **1:08** | **1:30** | intro ← our new opening |
| 1:30 | 1:58 | intro |
| 1:58 | 2:12 | verse |
| 2:12 | 2:26 | verse |
| 2:26 | 3:02 | verse |
| 3:02 | 3:30 | outro |
| 3:30 | 3:43 | chorus |
| **3:43** | **3:55** | outro ← repetitive loop / creative exit zone |

BPM: 136 · Bar: ~1.765s · Key: C major · 4/4

---

## Cut Decisions

### Start point
- **61.56s** — bar-aligned downbeat closest to 1:01
- Brief 0.5s fade-in to avoid a hard click from jumping mid-track

### Creative ending
- The final outro (3:43 / 223.92s) is a ~6.5-bar repetitive loop
- Let it play 1 bar to establish the feel, then fade out over 2 bars
- **Fade-out starts:** 225.1s (bar 2 of the final outro)
- **Fade-out duration:** 3.5s (≈ 2 bars at 136bpm)
- **Hard cut at:** 228.63s (next clean downbeat after fade completes)

### Result
- Input window: 61.56s → 228.63s
- Duration after trim: **167.07s ≈ 2:47**
- Relative fade-out: starts at 163.54s into the trimmed clip, lasts 3.5s

## Operations
1. `trim` — start=61.56s, duration=167.07s
2. `fade_in` — 0.5s at t=0 (avoids entry click)
3. `fade_out` — 3.5s starting at 163.54s (relative) — exits during the repetitive loop

## Output
- `testing/02/chicago-cut-v2.mp3`
- Original: 3:55 → Result: ~2:47
