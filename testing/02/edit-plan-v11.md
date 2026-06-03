# Chicago — Edit Plan v11

## Changes from v10

### 1. other_ambient — no EQ, minimal reverb
- Remove EQ entirely — cello/strings frequency content IS their character
- Reverb: wet=0.12, reverb_type="room" (small, intimate — just adds air, doesn't wash)
- Volume: 0.2 (was 0.3)
- Strings blend the middle phrase naturally without artificial processing

### 2. 2:29 transition — crossfade instead of switch
- v10: drums taper 0.3s, piano_end starts at full volume instantly → room switch audible
- v11: drums taper **1.5s**, piano_end **fades in over 1.5s** — proper crossfade at boundary
- other_ambient already fades out over 1.5s — all three now move together
- Nothing switches on/off, everything dissolves into the next state

### 3. Piano end — lower filter_sweep ceiling
- freq_ceil: 18000 → **8000Hz**
- Drum bleed in other.wav is constant in absolute level but becomes perceptually dominant
  when the musical signal fades (rms drops from 0.087 at 2:40 to 0.002 at 2:47)
- 8kHz high-cut is applied from 2:29, eliminating drum bleed before it surfaces
- curve=2.5 keeps cutoff near 8kHz early (barely audible), closes to 200Hz by end

### 4. Fade — starts 2:44, lasts 5s
- v10: fade applied over full 20s section (too early, buried the last chord)
- v11: full volume 2:29 → 2:44, then fade 2:44 → 2:49 (5s only)
- Last chord at ~2:40-2:44 remains fully audible

---

## Transition anatomy at 2:29
| What | Before 2:29 | 2:29 → 2:30.5 | After 2:30.5 |
|------|-------------|---------------|--------------|
| drums | full | fading (1.5s) | silent |
| other_ambient | fading out (1.5s ramp started 2:27.5) | continues fade | silent |
| piano_dry | full | fading (0.3s) | silent |
| piano_end | silent | **fading in (1.5s)** | full (processed) |

---

## Cumulative lessons
1. Segment label "chorus" = vocals enter → cut vocals before boundary
2. Sustained sources create reverb wash; transients (kick) create isolated blooms
3. Transparent sweep: high freq_ceil + steep curve avoids spectral step
4. Never xfade_join time-aligned stems — additive mixing on single timeline
5. Reverb on reverb = bloom — terminate ambient stems before second chain
6. Drum bleed is constant; it surfaces when musical signal fades → filter early
7. Strings/cello: no EQ before reverb, light reverb only — preserve natural warmth
8. Simultaneous switches sound harsh — stagger or crossfade transitions

---

## Key timestamps
| Event | Clip | Original |
|-------|------|---------|
| Start | 0:00 | 1:01.56 (61.56s) |
| Outro phrase A (full band) | 2:01 | 3:02.56 (182.56s) |
| Bass + vox cut, other_ambient fades in | 2:15 | 3:16.68 (196.68s) |
| Drums crossfade out / piano_end crossfades in | 2:29 | 3:30.90 (210.90s) |
| Fade starts | 2:44 | 3:45.56 (225.56s) |
| End | 2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v11.mp3`
