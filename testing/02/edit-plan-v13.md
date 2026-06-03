# Chicago — Edit Plan v13

## Changes from v12

### 1. Drums — gradual volume fade from 2:15 → 2:29
- `fade(1.0→0.0)` applied to drums from cut_samp (2:15) to sweep_samp (2:29) — 14.22s
- Drums naturally thin out through the middle phrase instead of staying loud until the last bar
- By the time filter_sweep starts (2 bars before 2:29), drums are already at ~25% volume

### 2. Drums — filter_sweep starts 2 bars early to avoid click
- v12: filter_sweep started at bar_samp (209.135s) cold onto a kick transient → click
- Root cause: kick RMS jumps 0.138→0.245 right at bar_samp — IIR filter initialization overshoots
- v13: filter_sweep starts 2 bars earlier (207.37s abs / 145.81s rel) with freq_ceil=16000Hz
  - Filter warms up at near-transparent 16kHz, drums already at 25% volume
  - No audible discontinuity when kick hits mid-sweep
  - 16000→80Hz over 3.53s (2 bars) with curve=1.5

### 3. Reverb — slightly drier
- wet: 0.55 → 0.38

---

## Why the click happened (v12)
`filter_sweep` uses `sosfilt_zi * seg[ch, 0]` to initialize filter state.
When seg[ch, 0] is a high-amplitude kick attack (peak=0.39), the initialization
vector is large — the filter overshoots on its first output samples → click.
Starting earlier with lower amplitude (25% of original) eliminates this entirely.

---

## Drum exit anatomy (v13)
| Time | drums volume | drums frequency |
|------|-------------|----------------|
| 0 → 2:15 | 1.0 | full bandwidth |
| 2:15 → 2:26 | 1.0→0.25 (fade) | full bandwidth |
| **2:26 → 2:29** | **0.25→0 (fade continues)** | **16kHz→80Hz sweep** |
| 2:29+ | silent | — |

---

## Cumulative lessons
1. Segment label "chorus" = vocals enter → cut before boundary
2. Sustained sources create reverb wash; transients don't
3. IIR filter initialization overshoots on high-amplitude first samples → start filter when signal is quiet
4. Parallel reverb copy smears stems — remove if stem sounds colored
5. Transparent sweep (high freq_ceil + steep curve) avoids spectral step
6. Never xfade_join time-aligned stems
7. Drum bleed surfaces when signal fades → filter early
8. Simultaneous switches sound harsh — crossfade or stagger

---

## Key timestamps
| Event | Clip | Original |
|-------|------|---------|
| Start | 0:00 | 1:01.56 (61.56s) |
| Outro phrase A — full band | 2:01 | 3:02.56 (182.56s) |
| Bass + vox cut, drums begin fading | 2:15 | 3:16.68 (196.68s) |
| Drums filter_sweep starts (16kHz, warm) | 2:25.81 | 3:27.37 (207.37s) |
| Piano exit begins (0.5s fade-in) | 2:29 | 3:30.90 (210.90s) |
| Fade-out starts | 2:44 | 3:45.56 (225.56s) |
| End | 2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v13.mp3`
