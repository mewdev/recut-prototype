# Chicago — Edit Plan v4

## User Intent
> Start from ~1:01. Outro: phrase A with full band, phrase A repeat with piano only, new phrase (chorus) — sweep + reverb + fade.

---

## Phrase Structure (outro region)

| Clip time | Original time | Event | Arrangement |
|-----------|--------------|-------|-------------|
| 0:00 | 1:01.56 (61.56s) | new start | full mix (via stems) |
| 2:01 | 3:02.56 (182.56s) | **outro — phrase A** | full band (drums + bass + piano + vocals) |
| **2:15** | **3:16.56 (196.68s)** | **phrase A repeat** | **piano only — drum cut on this downbeat** |
| 2:29 | 3:30.56 (210.90s) | **chorus / new phrase** | piano only → creative exit begins |
| ~2:50 | ~3:51 (231s) | end | silence |

---

## Drum Cut Design
- **Hard cut on downbeat at 196.68s abs / 2:15 clip**
- Short 0.3s fade to avoid click — inaudible as a fade, just smooths the transient
- No gradual fade: drums should be gone when phrase A repeat starts — clean structural cut at the bar

## Creative Exit (from 2:29 / 210.90s abs)
Piano only for ~20 seconds, with:

1. **filter_sweep** — `direction="close"`, sweeps from 8000Hz → 200Hz over 20s
   - `curve=0.6` — opens quickly then slows (highs leave fast, lows linger)
   - Gradually closes off brightness, leaving only warm low-end warmth
2. **reverb** — `reverb_type="hall"`, `wetness=0.55`
   - Large hall: long tail, bright-to-dark matches the sweep
   - Makes the piano feel like it's dissolving into a large space
3. **fade_out** — final 4s fade (last bar of the final outro, ~227s abs)

Total creative exit duration: ~20s (2:29 → ~2:50)

---

## What the Map Missed (and what needs to change)

### Problem: segment granularity too coarse
The map labeled `3:02 → 3:30` as a single `"outro"` block (28s = 16 bars).
Internally this is **two 8-bar phrases** (A + A-repeat) — but the map has no sub-segment markers.

**Consequence:** there was no way to infer from the map alone that 2:15 (bar 9) is a phrase boundary, not an arbitrary point. I defaulted to "halfway through = bar 9 = drop point", which coincidentally landed correctly — but for the wrong reason.

### What the map needs
1. **Phrase-level segmentation** — break segments at phrase boundaries (every 4–8 bars), not just at section changes. The `segments` array should have entries at 182.46s *and* 196.68s with labels like `"outro_A"` / `"outro_A_repeat"`.
2. **Repetition flag** — a boolean or score indicating whether a segment is a literal repetition of the previous one vs. new content. This is the key signal for "drop the drums when it repeats."
3. **Arrangement density curve** — a per-frame energy measure broken out by stem (drums, bass, melody). The drum drop point would be visible as a cliff in drum energy. This doesn't exist in the current map — only the full mix energy is implied.

---

## Implementation Plan
1. Mix stems (drums + bass + other + vocals) from 61.56s → 196.68s, drums/bass/vocals hard-cut at 196.68s (0.3s taper)
2. Piano-only (other.wav) from 196.68s → end, aligned to stems
3. Apply `filter_sweep(direction="close", freq_floor=200, freq_ceil=8000, duration=20, curve=0.6)` starting at 210.90s abs
4. Apply `reverb(reverb_type="hall", wetness=0.55)` to the same region
5. `fade_out` last 4s
6. 0.5s fade-in at clip start

## Output
- `testing/02/chicago-cut-v4.mp3`
- Duration: ~2:50
