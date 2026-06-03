# Skill: Effects Routing

Which primitives to use on which stem types, and when. Wrong routing produces resonance artifacts, bass buildup, and audible processing boundaries.

---

## Source Type → Correct Primitive

| Source type | Volume exit | Frequency exit | Reverb |
|-------------|-------------|----------------|--------|
| **Kick / drums** | `fade` (volume only) | ❌ never `filter_sweep` | EQ first at ≥400Hz high-pass, then `reverb` if needed |
| **Bass** | `fade` | `eq` static lowpass if needed | Rarely — bass reverb muds low-end |
| **Piano / pads** | `fade` | `filter_sweep` ✓ | `reverb` ✓ |
| **Strings / cello** | `fade` | `filter_sweep` ✓ | Very light `reverb` (wet≤0.15, "room") — preserve attack clarity |
| **Vocals** | `fade` | `eq` static | `reverb` ✓ but watch timing relative to segment boundaries |

---

## filter_sweep — When and How

`filter_sweep` applies a time-varying IIR lowpass. Sounds musical on **sustained pitched sources** (piano, strings, pads, bass sine).

**Never use on percussive/transient sources (kicks, snare, percussion):**
- 2nd-order Butterworth resonance peaks at ~1kHz (ring_tail_rms 80× higher than at 8kHz)
- Each kick transient excites the resonance → audible tonal ring at the cutoff frequency
- Equal-loudness curve peaks at 1–4kHz → maximally perceptible

**Parameters for creative exit (close direction):**
```python
filter_sweep(piano_seg, sr,
    direction="close",
    freq_ceil=8000,    # start here — slight initial high-cut eliminates drum bleed
    freq_floor=200,    # muffled but musical end state
    curve=2.5,         # stays near freq_ceil longer, drops fast near end
    duration=20.0,     # cover the full exit section
)
```

**For transparent start (no audible step at transition):**
- Set `freq_ceil=18000` — filter is perceptually inaudible at t=0
- Use `curve=2.5` — frequency stays near ceiling for the first half, drops quickly at end

---

## reverb — When and How

**On drums:** EQ first. High-pass at ≥400Hz before reverb to remove kick fundamental (60–100Hz). Without this, each kick creates a 1s low-frequency bloom that accumulates.

**Wetness guide:**
- `wet=0.85+` → fully ambient / ghost (no dry signal) — use when drums should "dissolve"
- `wet=0.55` → hall send — room feel, still clearly the source
- `wet=0.38` → subtle space — adds air, source stays forward
- `wet=0.12` → very light / "room mic" — use for strings where attack clarity must be preserved

**Reverb on reverb = bloom.** If a stem already has reverb applied, do not route it into a second reverb chain. Zero out reverb stems before a second `reverb` call.

**Preset guide:**
- `"room"` — small, intimate. Good for strings/cello ambient layer
- `"hall"` — large, spacious. Good for piano exits and ghost drums
- `"plate"` — bright, washy. Good for vocals

---

## eq — Static Filter

Use for:
- High-passing drums before reverb: `eq(drums, sr, cutoff=400, type="high")`
- Softening exposed stem attacks: `eq(piano_dry_zone, sr, cutoff=4000, type="low")`
- Removing rumble from vocals: `eq(vox, sr, cutoff=80, type="high")`

**Never EQ strings/cello before reverb** — their low-mid warmth is their character. Filtering removes it.

---

## Chain Ordering

When composing multiple effects, order matters:

```
# Correct for drums ghost:
eq(high-pass) → reverb

# Correct for piano exit:
filter_sweep → reverb → fade

# Wrong (reverb then filter_sweep amplifies reverb tail artifacts):
reverb → filter_sweep
```

**General rule:** EQ first, reverb second, volume envelope last.
