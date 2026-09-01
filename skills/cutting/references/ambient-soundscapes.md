# Ambient Soundscapes

A different brief from the rest of this skill: not editing a song's structure, but
building a generative-feeling ambient/drone piece *from* one or two of its fragments —
"Fripp/Eno style," "dreamy soundscape," "tape loop," "seamless ambient loop." Same
primitives as everywhere else (`Clip`, `loop`, `fx`, `chain`), a different arrangement
pattern. This file is the fast path — the mechanics behind it are already in
`effects-routing.md` (Delay feedback ranges, gain staging), `known-limitations.md`
(partial-clip effects, `chain()` reprocessing), and `map-interpretation.md`
(`bpm` verification) — read those if something here is unclear.

## 1. Pick source material — drum-free, and check the seam

Ambient work wants sparse, sustained, drum-free material — the opposite of what makes a
good chorus hook. Look at `EnrichedSegment.loudness_db` (quietest sections) and
`segment_name` (`inst`/`bridge`/`intro` are more likely drum-light than `chorus`); the
map has no direct instrument-activity signal (see `known-limitations.md`), so this is a
judgment call, not a lookup.

**Before looping or splicing two fragments, check they land on the same or a
compatible chord** at the seam — pull `EnrichedSegment.chords` for both points. Two
fragments ending on the same chord loop/splice coherently; a splice between unrelated
chords reads as a wrong note, no matter how good the effects are. This is a `music-theory`
skill judgment, not this file's — load it alongside for anything beyond "do these two
chords match."

## 2. One `Clip(loop=N, fx=[...])`, not several `Clip`s joined by `XFade`

This is the single most important structural lesson from building these: **don't**
build an ambient piece as several differently-processed `Clip`s (e.g. escalating
wetness) joined by `XFade`. It reads as harsh, jarring parameter jumps at each seam,
not a smooth evolution — confirmed by ear, repeatedly, before landing on the right
approach. Use one `Clip` with `loop=N` and a single, fixed `fx` chain instead:

```python
Clip("inst", offset_bars=4, loop=8, fx=[
    FilterSweep(filter_type="high", freq_start=200, freq_end=200),
    FilterSweep(filter_type="low", freq_start=1400, freq_end=1400),
    Delay(delay_seconds=0.7, feedback=0.9, mix=0.15),
    Reverb(wetness=0.65, reverb_type="hall", room_size=0.97, damping=0.12),
])
```

Why this is structurally better, not just simpler: `loop` repeats the raw audio
*before* `fx` runs (`api-reference.md`), so `Delay`/`Reverb` process the whole looped
buffer in one continuous pass — no per-repeat reverb-restart, which a multi-`Clip`
chain can't avoid regardless of how smooth the `XFade`s are. The raw loop repeats do
have a hard concatenation seam internally (checked: ~0.12 amplitude jump on a typical
fragment) — in practice the low-pass + heavy reverb below diffuses it enough to not
read as a click, but if it's audible after listening, the fix is the same taper
technique used for `_reverb_tail_padding` (`src/recut/compositor/__init__.py`), not yet
generalized into `loop` itself.

## 3. Effect chain recipe

Static filters first, `Delay` next, `Reverb` last (standard chain-ordering rule) —
for this specific "dreamy" character:

- **High-pass ~180-220Hz** — always, strips sub-bass that would otherwise bloom under
  heavy reverb (`effects-routing.md`'s bass-bloom rule).
- **Low-pass, pushed low (~1200-1800Hz) for genuinely dreamy/dark** — the first pass at
  ~2500-3000Hz still let audible high-end transients through; went lower on user
  feedback ("still not there, but closer" → then lower again). Start around 1500Hz for
  "dreamy," not 3000Hz.
- **`Delay(feedback=0.85-0.95)`** — continuous wash, not discrete echo (see the
  feedback-range table in `effects-routing.md`); lower feedback here specifically read
  as an awkward "clap" artifact.
- **`Reverb(reverb_type="hall", room_size≈0.95-0.97, damping≈0.12-0.15, wetness=0.5-0.65)`**
  — override `room_size`/`damping` past the presets rather than relying on `reverb_type`
  alone when "longer reverb" is the ask: bigger `room_size` + lower `damping` lengthens
  the decay, independent of the low-pass handling brightness. Don't conflate the two —
  each control owns one job.

## 4. Duration and pacing

Target duration ÷ fragment duration ≈ `loop` count, then subtract a bit for the
auto tail-padding compose() adds when the last (only) clip has `Reverb`/`ReverbSweep`
(`1.5 + 2.5 * room_size` seconds — `effects-routing.md`). A ~1-minute piece from a
~7.7s fragment: `loop=8` (≈62s raw + ~3.9s tail ≈ 66s). No `XFade` overlap to net out
against, unlike a multi-`Clip` chain — the whole raw-repeat length counts.

## 5. Verify before calling it done

- **Peak amplitude** — `np.abs(result.samples).max()` should be ≤~1.0. High-feedback
  `Delay` + wet `Reverb` can build gain; check especially before any reprocessing pass
  (below).
- **Spectral check for "still too bright"** — quick FFT, sum energy above ~4kHz as a
  fraction of total, to confirm a low-pass change actually moved the brightness before
  re-rendering and asking the user to re-listen.
- **Loop-seam step size** — `np.diff()` around each `k * fragment_duration` boundary,
  compared against the file's own overall step-size distribution (mean/p99), not an
  absolute threshold — tells you whether the internal loop seam is actually elevated
  above the piece's normal grain or not.

## 6. Deepening: reprocess the render itself

"Bounce and reprocess" (run an already-rendered mix through the same chain again) is a
real, useful technique here and the API already supports it — at the `chain()` layer,
not `compose()` (no map/segment context needed or wanted for a second pass over a
finished mix). See `known-limitations.md` for why `compose()` doesn't reach this case
yet (issue #52). **Must peak-normalize between passes** — this is where the clipping
bug actually happened (two passes of `feedback=0.9`, no normalization, peak hit 5.56).
Full code and the `peak_normalize()` snippet: `effects-routing.md`'s "Gain staging"
section.

## Quick checklist for next time

1. Pick drum-free source(s), verify chord compatibility at any splice/loop seam.
2. One `Clip(loop=N, fx=[...])`. No `XFade` between differently-processed repeats.
3. High-pass (~200Hz) → low-pass (~1200-1800Hz for "dreamy") → `Delay` (feedback
   0.85-0.95) → `Reverb` (`room_size`/`damping` overridden for tail length, wetness
   0.5-0.65).
4. `loop` count from target duration ÷ fragment duration, minus a little for tail-padding.
5. Check peak amplitude, spectral brightness, and loop-seam step size before calling it done.
6. If reprocessing a render for extra depth: `chain()`, not `compose()`, and normalize
   between passes.
