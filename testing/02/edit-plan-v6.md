# Chicago — Edit Plan v6

## Changes from v5
- **New `eq` primitive** — general Butterworth filter, type is a parameter
- **Drums reverb chain:** `eq(high, 120Hz) → reverb(wet=1.0)` instead of `reverb(wet=0.85)`
- Everything else identical to v5

## Problem with v5
Reverbing the full drum stem at wet=0.85 kept 15% dry signal AND passed the kick's
60–100Hz fundamental into the reverb — each hit created a ~1s low-frequency bloom.
Multiple kicks accumulated into a constant bass rumble that summed with the bass stem.

## Fix
High-pass the drum stem at **120Hz** before reverb:
- Removes kick fundamental, preserves attack transient + upper harmonics (snare crack, hi-hat)
- Reverb at **wetness=1.0** (pure wet) — no dry drums in the ghost zone
- Result: airy, spatial rhythm without any bass content

```
chain(drums, sr,
    (eq,     dict(cutoff=120, type="high")),   # kill kick low-end
    (reverb, dict(wetness=1.0, reverb_type="hall")),
)
```

## Lessons learned

1. **Reverb + kicks = bass mud** — kick fundamentals (60–100Hz) get stretched into sustained
   low-frequency tails by reverb. Always high-pass drums before reverb.

2. **100% wet for ambient ghost drums** — when the goal is "rhythm implied, not driven",
   dry=0 is correct. Any dry signal re-introduces the percussive attack you're trying to dissolve.

3. **Never xfade_join time-aligned stems** (from v4→v5) — `xfade_join` overlaps content,
   shifting timing and causing phase doubling on continuous stems. Additive mixing on a
   single timeline is the right approach.

4. **EQ belongs as a general primitive** — high-pass, low-pass, band are the same operation
   with different `type` parameters. A separate `highpass` primitive would be redundant.

## Key timestamps (unchanged)
| Event | Clip time | Original time |
|-------|-----------|--------------|
| New start | 0:00 | 1:01.56 (61.56s) |
| Outro phrase A (full band) | 2:01 | 3:02.56 (182.56s) |
| Phrase A repeat — reverb drums | 2:15 | 3:16.68 (196.68s) |
| Chorus — sweep + reverb begins | 2:29 | 3:30.90 (210.90s) |
| End | ~2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v6.mp3`
