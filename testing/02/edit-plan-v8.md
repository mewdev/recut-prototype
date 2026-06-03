# Chicago — Edit Plan v8

## Changes from v7

### 1. Middle phrase (2:15–2:29): add `other_ambient` layer
- `other.wav` → `reverb(wet=0.75, hall)` × 0.35 volume
- Piano sustains create a continuous reverb wash that the kick reverb sits in
- Fades in over 0.5s at cut_samp, fades out over 1.5s ending at sweep_samp

### 2. Drums_rev: wetness 0.7 → 0.85
- More ambient, blends into the other_ambient wash rather than sitting on top of it

### 3. 2:29 transition fix: sweep starts at 2:15 transparently
- v7: filter_sweep started at sweep_samp (2:29) → instant spectral drop → audible thud
- v8: filter_sweep applied to piano from cut_samp (2:15), duration=34.32s (full remaining clip)
  - freq_ceil=20000Hz (effectively transparent at t=0)
  - freq_floor=200Hz
  - curve=2.5 (close direction: stays near 20kHz a long time, drops fast at the end)
  - At 2:29 (14s in): cutoff ≈ 12kHz — inaudible filtering
  - At 2:49 (34s in): cutoff = 200Hz — fully muffled
- No abrupt spectral change at any boundary

### 4. Reverb + fade still applied from sweep_samp (2:29) on the already-swept piano
- reverb(wet=0.55, hall) on piano from 2:29 → end
- fade(1.0→0.0) over the entire sweep section

---

## Signal path

| Region | piano | bass | vox | drums_dry | drums_rev | other_ambient |
|--------|-------|------|-----|-----------|-----------|---------------|
| 0 → cut_rel | unchanged | full | full | full | silent | silent |
| cut_rel → sweep_rel | swept (transparent) | silent | silent | silent | eq(400Hz)→rev(0.85) | rev(0.75)×0.35 |
| sweep_rel → end | swept+reverb+fade | silent | silent | silent | silent | silent |

## Insights (cumulative)

1. **Single-transient reverb = isolated blooms** — need a sustained source (piano reverb) as wash for it to read as "room"
2. **Sweep transparency trick** — starting filter_sweep with freq_ceil=20000Hz makes t=0 inaudible; gradual close over the full section removes all transition artifacts
3. **Reverb on reverb = bloom** (v5/v6 lesson) — terminate reverb stems before they enter another reverb chain
4. **High-pass drums before reverb at 400Hz** — 120Hz was not enough, kick body still accumulated
5. **Never xfade_join time-aligned stems** (v4 lesson)

## Key timestamps
| Event | Clip | Original |
|-------|------|---------|
| Start | 0:00 | 1:01.56 (61.56s) |
| Outro phrase A (full band) | 2:01 | 3:02.56 (182.56s) |
| Phrase A repeat — reverb drums + other_ambient, sweep begins transparently | 2:15 | 3:16.68 (196.68s) |
| Chorus — reverb added to piano, other_ambient fades out | 2:29 | 3:30.90 (210.90s) |
| End | ~2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v8.mp3`
