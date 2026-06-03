# Chicago — Edit Plan v14

## Single change from v13
Remove `filter_sweep` from drums entirely. Volume fade only.

## Why
2nd-order Butterworth resonance peaks at 1kHz (ring_tail_rms = 0.01677 vs 0.00011 at 8kHz).
The drum sweep passed through this range at 2:28 — each kick excited a tonal ring at the
cutoff frequency, audible as rhythmic clicks despite drums being at <10% volume.
Equal-loudness sensitivity also peaks at 1-4kHz, making these artifacts maximally perceptible.

`filter_sweep` is the right tool for sustained pitched sources (piano, pads, bass).
It is the wrong tool for transient-heavy percussive sources (kicks, snare).
For drums: scalar amplitude envelope only — zero resonance, zero artifacts.

## Drum exit (v14)
```
fade(drums[cut_samp:sweep_samp], vol_start=1.0, vol_end=0.0)
drums[sweep_samp:] = 0.0
```
Simple linear fade from 2:15→2:29. Drums thin out naturally. No filtering, no ringing.

## Everything else unchanged from v13
- bass + vox: cut at 2:15
- piano exit: filter_sweep(8kHz→200Hz, curve=2.5) + reverb(wet=0.38) + fade-out from 2:44
- 0.5s fade-in on piano_end

## Cumulative lessons
1. Segment label "chorus" = vocals enter → cut before boundary
2. Sustained sources create reverb wash; transients don't
3. IIR filter_sweep on percussive stems → resonance clicks — use volume fade instead
4. IIR initialization overshoots on high-amplitude first samples → start filter when quiet
5. Parallel reverb copy smears stem clarity — remove if audible
6. Transparent sweep (high freq_ceil + steep curve) avoids spectral step on pitched sources
7. Never xfade_join time-aligned stems
8. Drum bleed surfaces when signal fades → filter the receiving stem (piano), not the source (drums)
9. Simultaneous switches sound harsh — crossfade or stagger

## Key timestamps (unchanged from v13)
| Event | Clip | Original |
|-------|------|---------|
| Start | 0:00 | 1:01.56 (61.56s) |
| Outro phrase A — full band | 2:01 | 3:02.56 (182.56s) |
| Bass + vox cut, drums begin fading | 2:15 | 3:16.68 (196.68s) |
| Piano exit begins (0.5s fade-in) | 2:29 | 3:30.90 (210.90s) |
| Fade-out starts | 2:44 | 3:45.56 (225.56s) |
| End | 2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v14.mp3`
