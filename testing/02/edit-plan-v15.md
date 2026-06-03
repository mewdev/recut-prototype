# Chicago — Edit Plan v15

## Single change from v14
End drum fade at 2:25.78 (207.34s abs) instead of 2:29 (sweep_samp).
Drums completely silent from 2:26 → no kicks at 2:28-2:29.

## Why v14 still clicked
Linear fade ends at sweep_samp (2:29). At 2:28, drums are still at:
- 2:28.01: fade_amp=0.094, peak_faded=0.036
- 2:28.45: fade_amp=0.063, peak_faded=0.024
- 2:28.89: fade_amp=0.032, peak_faded=0.012

Piano at same positions: peak=0.150, 0.153, 0.140
Drums at -12 to -21dB below piano.

Sustained tone masking requires ~40dB. Transient kicks bypass this —
the auditory onset detector fires independently of steady-state masking.
Even at -21dB, a kick transient pops through sustained piano content.

## Fix
Fade drums from cut_samp (2:15) to DRUM_FADE_END (207.34s abs = 2:25.78).
Duration: 10.66s instead of 14.22s.
drums[drum_fade_end_samp:] = 0.0

Last 3.56s (2 bars) before piano exit: completely silent drums.
Beats at 2:28-2:29: zero amplitude, zero transients, zero clicks.

## Cumulative lessons
1. Segment label "chorus" = vocals enter → cut before boundary
2. Sustained sources create reverb wash; transients don't
3. IIR filter_sweep + percussive stems = resonance clicks — volume fade only for drums
4. Parallel reverb copy smears stem clarity
5. Transparent sweep (high freq_ceil + steep curve) avoids spectral step
6. Never xfade_join time-aligned stems
7. Linear fade does not suppress transients — auditory onset detector bypasses masking
   → reach zero BEFORE the transient zone, not at it
8. Drum bleed surfaces when signal fades → filter the receiving stem not the source

## Key timestamps
| Event | Clip | Original |
|-------|------|---------|
| Start | 0:00 | 1:01.56 (61.56s) |
| Outro phrase A — full band | 2:01 | 3:02.56 (182.56s) |
| Bass + vox cut, drums begin fading | 2:15 | 3:16.68 (196.68s) |
| **Drums reach zero (2 bars early)** | **2:25.78** | **3:27.34 (207.34s)** |
| Piano exit begins | 2:29 | 3:30.90 (210.90s) |
| Fade-out starts | 2:44 | 3:45.56 (225.56s) |
| End | 2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v15.mp3`
