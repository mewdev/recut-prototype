# Changelog

## [edit 2.4] — 2026-05-29 — Current best
**Track:** labour.mp3 (B minor, 83 BPM)
**Cut:** 51.15s – 89.01s (chorus body, 37.86s)

Two-layer ending with BPM-synced delay tail extending 5s past cut end.
- Layer 1 (dry): full body, 2s fade at the very end
- Layer 2 (wet): delay (1 beat @ 83 BPM) + hall reverb, fades in over 2s, fades out over tail
- Intro: 6s filter sweep (low→full open) + volume fade-in + hall reverb + 80ms silence pad
- Click fixes: warmup > 1 delay cycle (1.22s), micro-fades at both boundaries of ending_src
- Primitive used: `chain()` for intro and wet layer composition

**Known limitation:** relies on full mix (mono stem). Cleaner intro/outro would use separated stems — guitar loop for intro sweep, isolated vocals for ending layer.

---

## [edit 2.3] — two-layer mix, bell-curve wet envelope
- Dry fades 1→0 over last 5s, wet fades 0→peak→0 (bell curve)
- Wet still ended at CUT_END — no tail extension
- Issue: bell curve ended too abruptly, no delay ring-out

## [edit 2.2] — two-layer ending, first working version
- Dry fades out, wet (delay+reverb) runs underneath
- Issue: delay time not BPM-synced, hard cut at layer boundary

## [edit 2.1] — ending zone with filter close + delay + fade
- Last 5s: half-beat delay → filter sweep close (full→300Hz) → fade out
- Issue: hard join between body and ending zone, felt forced

---

## [edit 1.5] — intro with hall reverb  *(split from 1.4 for preservation)*
- Adds reverb(wetness=0.5, hall) after filter sweep
- Initial click fix: fade applied before reverb, 80ms silence prepended
- Best non-layered version

## [edit 1.4] — filter sweep intro, no reverb
- 6s pre-roll: filter sweep open (220Hz→20kHz, curve=6) + fade(0.2→1.0)
- First clean sweep without click
- `filter_sweep` primitive with direction, freq_floor, freq_ceil, curve params

## [edit 1.3] — filter sweep with parametrized curve
- Introduced logarithmic frequency interpolation, curve parameter
- 1024-step zi carry-over approach — eliminated sweep clicks

## [edit 1.2] — filter sweep with separate volume fade
- Split `filter_sweep` (frequency only) from `fade` (volume only)
- User feedback: "fade in and out volume wise should be different thing"

## [edit 1.1] — first filter sweep
- Low-pass filter sweeps open from 100Hz to full over 6s
- `filter_sweep` primitive, scipy Butterworth, blend approach

## [edit 1.0] — basic cut
- User prompt: "keep only 0:51–1:29"
- Hard cut at 51.15s–89.01s, xfade join to main body
- Established: cut, xfade primitives

---

## Primitives developed this prototype phase

| Primitive | Description |
|-----------|-------------|
| `cut` | hard slice [start, end] in seconds |
| `fade` | linear volume envelope |
| `filter_sweep` | DJ-style low-pass sweep, direction + curve |
| `reverb` | pedalboard Reverb, room/hall/plate presets |
| `delay` | pedalboard Delay, BPM-syncable |
| `xfade_join` | equal-power crossfade join between two segments |
| `chain` | compose effects: `chain(audio, sr, (fn, kwargs), ...)` |
