# Chicago — Edit Plan v3

## User Intent
> "Start from ~1:01 till end. Beginning from outro — first repetition with drums, then drums disappear and only piano stays."

Start mid-track, ride through full arrangement into the outro, strip to piano-only for a quiet, intimate ending.

---

## Song Structure (full)
| Abs time | Rel time | Section | Arrangement |
|----------|----------|---------|-------------|
| 0:00 | — | verse/chorus | *skipped* |
| **1:01.56** | **0:00** | outro | ← our new start |
| 1:08.66 | 0:07 | intro | full mix |
| 1:30.00 | 0:28 | intro | full mix |
| 1:58.46 | 0:57 | verse | full mix |
| 2:12.67 | 1:11 | verse | full mix |
| 2:26.89 | 1:25 | verse | full mix |
| **3:02.45** | **2:00** | outro | full mix → **drum drop at bar 9** |
| 3:30.44 | 2:29 | chorus | piano only |
| 3:43.92 | 2:42 | final outro | piano only → fade |

BPM: 136 · Bar: ~1.765s · Key: C major · 4/4

---

## Creative Ending — Drum Drop Design

### Why bar 9 of the outro (196.68s)?
- The outro is 16 bars (182.46s → 210.44s)
- Splitting at bar 9 = first 8 bars full, last 8 bars piano = symmetric, musical
- 196.68s is a confirmed downbeat — clean bar alignment
- The chorus that follows (3:30) then arrives already "stripped", making it feel like an intimate reprise

### Transition (196.68s absolute / 2:00 relative into trimmed clip)
- Crossfade duration: **3.5s** (≈ 2 bars) — long enough to feel intentional, short enough not to smear
- **Fade out:** drums + bass + vocals stem volumes → 0 over 3.5s
- **Result:** only `other.wav` (piano) remains from 196.68s onward

### Final exit
- Piano carries through: 8 bars outro + 8 bars chorus + final outro loop
- **Fade-out starts:** 228.63s absolute (bar 2 of final outro, 167.07s relative)
- **Fade-out duration:** 4s → ends at 232.63s

---

## Implementation: Stem Mixing Strategy

Build from stems (drums.wav, bass.wav, other.wav, vocals.wav) to allow independent volume control:

**Phase 1 — Full mix from stems (61.56s → 200.18s):**
- All 4 stems summed at equal volume
- At 135.12s relative (=196.68s absolute): begin fading drums+bass+vocals to 0 over 3.5s

**Phase 2 — Piano only (200.18s → 232.63s):**
- Only other.wav, at full volume
- Final 4s fade-out starting at 167.07s relative

The stem sum will sound slightly different from the original master (no limiting/compression), but for this prototype it's the cleanest way to execute the drop.

## Key Timestamps
| Event | Absolute | Relative to trim |
|-------|----------|-----------------|
| New start | 61.56s | 0:00 |
| Outro begins | 182.46s | 2:00.90 |
| **Drum drop (bar 9)** | **196.68s** | **2:15.12** |
| Crossfade complete | 200.18s | 2:18.62 |
| Chorus (piano only) | 210.90s | 2:29.34 |
| Final outro loop | 223.92s | 2:42.36 |
| Fade-out starts | 228.63s | 3:07.07 |
| **End** | **232.63s** | **~2:51** |

## Output
- `testing/02/chicago-cut-v3.mp3`
- Original: 3:55 → Result: **~2:51**
