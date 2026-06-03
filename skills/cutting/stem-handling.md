# Skill: Stem Handling

Rules for working with separated stems. Violating these produces timing artifacts, phase issues, and audible joins.

---

## Core Rule: Single Continuous Timeline

**Never split a stem and rejoin it with `xfade_join`.**

`xfade_join(a, b, xfade_ms)` overlaps the tail of `a` with the head of `b`. For time-aligned stems, this shifts the content of `b` earlier by `xfade_ms`, destroying bar alignment. Additionally, if both segments contain the same source (e.g., piano), the overlapping copies play at different time offsets → phase smearing.

**Correct approach:** build everything as additive layers on a single shared timeline. Zero out the parts you don't want. Never concatenate.

```python
# WRONG
full = xfade_join(section_a, section_b, xfade_ms=300, sr=sr)

# RIGHT
mix = combine_stems(piano, drums, bass, vox)  # full timeline
drums[:, cut_samp:] = 0.0                     # zero what you don't want
```

---

## Taper vs Hard Cut

**Hard cut (no taper):** audible click if signal is non-zero at cut point.
**Short taper (0.3s):** use for any stem that is active at the cut point.
**Longer taper (1.5s+):** use when you want a perceptible fade — but be aware that transient sources (kicks) remain audible even at low amplitude.

```python
# 0.3s taper — remove click, not perceptible as fade
stem[:, cut_samp : cut_samp + int(0.3*sr)] *= np.linspace(1.0, 0.0, int(0.3*sr))
stem[:, cut_samp + int(0.3*sr):] = 0.0
```

---

## Taper Timing Rule

**Reach zero BEFORE the next audible transient, not at it.**

A linear fade from 1.0→0.0 ending at time T still has non-zero amplitude on the beats immediately before T. Kick transients at 6–12% amplitude bypass psychoacoustic masking and are heard as clicks — especially in a quiet mix where previously-masking instruments have left.

**Rule:** if drums must be silent by beat N, end the fade by beat N-2 (2 bars early).

---

## Stem Content — Don't Assume

| Stem | Typical content | Watch for |
|------|----------------|-----------|
| `drums.wav` | Kick, snare, hi-hat | May be kick-dominated if song has sparse percussion |
| `bass.wav` | Bass guitar/synth | Often has harmonic overtones up to 300Hz |
| `other.wav` | Everything else | May contain cello, strings, piano, synth pads — **check before processing** |
| `vocals.wav` | Lead vocals | Check RMS at segment boundaries — vocals often enter at chorus |

**Always measure RMS per section before deciding what to do with a stem.**

---

## Checking What's in a Stem

```python
# Quick RMS + hi_ratio check for any stem in a time window
with AudioFile('other.wav') as f:
    f.seek(int(start_abs * sr))
    seg = f.read(int(dur * sr))
rms = np.sqrt(np.mean(seg**2))
hi = sosfilt(butter(4, 4000/nyq, 'high', output='sos'), seg, axis=-1)
hi_ratio = np.sqrt(np.mean(hi**2)) / rms
# hi_ratio < 0.02 → mostly low-mid (strings, bass, piano body)
# hi_ratio > 0.1  → bright content or drum bleed
```

---

## Drum Bleed Detection

Stem separation is imperfect. Other stems may contain drum bleed. To detect:

1. Compare 1ms RMS shape in suspect stem vs drums stem — correlated attack shape = bleed
2. Compare on-beat vs off-beat peak at 10ms window — consistent spike ratio at beats = bleed
3. Check hi_ratio over time — sudden jump when musical signal fades = bleed becoming dominant

**Note:** temporal masking means drum bleed in other stems was often hidden by the actual drums. When drums are removed, bleed in other stems can become audible.
