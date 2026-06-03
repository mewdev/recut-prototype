# Chicago — Edit Plan v16

## Single change from v15
Apply `eq(cutoff=4000, type="low")` to piano_dry in the exposed zone only:
from drum_fade_samp (2:25.78) to sweep_samp (2:29).

## Why
Click at 2:28 is the cello/piano's own rhythmic attack exposed after drums leave.
- No drum bleed confirmed (1ms RMS shape in other.wav is uncorrelated with drums)
- Spike at beat position: only 1.41x at one beat, 0.92-0.95x at others — not systematic bleed
- Root cause: kick was providing temporal forward-masking (~20ms) over cello attacks
  Remove kick → cello attack becomes the loudest transient → sounds like a click

## Fix
eq(piano_dry[drum_fade_samp:sweep_samp], cutoff=4000, type="low")
- Rounds off attack transients in the 3-second exposed window
- Other.wav is already 98.7% sub-4kHz energy (hi_ratio=0.013)
- 4kHz cut barely changes timbre — only affects the attack edge, not the body of the sound
- Applied to slice only — piano_end (from sweep_samp) is unaffected

## Cumulative lessons
1. Segment label "chorus" = vocals enter → cut before boundary
2. Sustained sources create reverb wash; transients (kick) don't
3. IIR filter_sweep + percussive stems = resonance clicks — volume fade only for drums
4. Parallel reverb copy smears stem clarity
5. Linear fade doesn't suppress transients — reach zero BEFORE the transient zone
6. Temporal masking is asymmetric: removing a masker exposes co-timed content in other stems
   → check all stems for exposed attacks after removing a percussive element
7. Drum bleed diagnosis: compare 1ms RMS shape, not just peak level

## Key timestamps (unchanged)
| Event | Clip | Original |
|-------|------|---------|
| Start | 0:00 | 1:01.56 (61.56s) |
| Bass + vox cut, drums begin fading | 2:15 | 3:16.68 (196.68s) |
| Drums reach zero | 2:25.78 | 3:27.34 (207.34s) |
| **eq(4kHz) applied to piano_dry** | **2:25.78–2:29** | **207.34–210.90s** |
| Piano exit begins | 2:29 | 3:30.90 (210.90s) |
| Fade-out starts | 2:44 | 3:45.56 (225.56s) |
| End | 2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v16.mp3`
