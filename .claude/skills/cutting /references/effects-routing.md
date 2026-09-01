# Effects Routing

Which of the 4 real effects (`Fade`, `Reverb`, `Delay`, `FilterSweep` — see `api-reference.md`) to reach for, and in what order. Wrong routing produces resonance artifacts, mud, or an audible processing boundary.

**All effects apply to the whole mix.** `compose()` takes one `Audio`; there is no per-instrument isolation (see `known-limitations.md`). Every rule below is about what the *whole mix* will sound like when you apply an effect, not about targeting one instrument inside it.

## No `eq` primitive

There isn't one. For a static (non-swept) filter — e.g. "high-pass the low end" or "dull the top" — use `FilterSweep` with `freq_start == freq_end`: the sweep math collapses to a constant cutoff when start and end match, regardless of `duration`.

```python
FilterSweep(filter_type="high", freq_start=400.0, freq_end=400.0)   # static high-pass at 400Hz
```

## `FilterSweep` — when and how

Real params: `filter_type` (`"low"`/`"high"`), `freq_start`, `freq_end`, `duration`, `curve` (a **numeric exponent**, not a curve name — `1.0` linear, `>1` lingers near `freq_start` longer then drops fast, `<1` moves fast then slows).

It's a 2nd-order Butterworth swept over the *entire clip it's applied to* — every transient in the mix (kick, snare, plucked attack) will interact with the filter's resonance at whatever frequency it's passing through at that instant. This is most audible/musical on sections where percussive content is already sparse or has already faded (an outro, a stripped-down bridge) — it reads as "the room closing in." Applied to a dense, drum-forward section, expect audible ringing/clicking as the sweep crosses the drums' frequency content.

**Transparent start** (no audible step where the effect begins): `freq_start` near the top of the audible range (e.g. `18000` for a `low` sweep) with `curve > 1` so the filter is near-inaudible at t=0 and descends later.

## `Reverb` — when and how

`wetness` (0.0 dry – 1.0 fully wet), `reverb_type` (`room`/`hall`/`plate`, sets `PRESETS` for `room_size`/`damping`/`width` — see `assets/effects-cheatsheet.md`), each preset field individually overridable.

- **Reverb-on-reverb = bloom.** If a clip's tail already carries reverb from an earlier effect in the chain (or from the source recording), a second `Reverb` accumulates into mud, not more space. Don't stack it.
- Applying `Reverb` to a section with prominent low end (bass-heavy, kick-driven) blooms in the low-mids — prefer a preceding static-filter `FilterSweep` high-pass (see above) before `Reverb` in that case.
- Higher `wetness` (`0.7+`) reads as "dissolving into space" — appropriate for exits, not mid-song.
- **Reverb tails on the composition's last clip get auto-padded.** When the *last* `Clip` in a sequence has `Reverb`/`ReverbSweep` in its `fx`, `compose()` (`src/recut/compositor/__init__.py`) appends trailing silence to that clip's audio before running the effect chain, sized `1.5 + 2.5 * room_size` seconds — enough room for the tail to actually decay instead of truncating at the clip boundary. This only applies to the composition's *final* clip (nothing to extend into for a mid-song `Reverb`, since the next `Clip` follows immediately) and only helps the reverb tail itself, not an unrelated hard cut elsewhere.
- **A fixed `wetness` steps in abruptly if the clip starts mid-composition.** `reverb()`'s mix is constant across the whole clip — the moment that `Clip` begins, the wet signal is already at full mix, which can read as "reverb suddenly appears." Use `reverb_sweep()`/`ReverbSweep` instead when you want the wet mix to build in gradually (`wetness_start` → `wetness_end` over `duration`, via the same envelope curve `fade` uses) rather than stepping in.

## `Delay`

`delay_seconds`, `feedback` (`0` = one echo, `1.0` = infinite repeats — use with care, this can run past the end of a clip), `mix`. Straightforward; the only routing rule is ordering (below) — a delay after a filter sweep inherits the swept tone into each repeat, which is usually what you want for an exit.

**`feedback` range determines the character, not just the repeat count:**

| `feedback` | Character | Use for |
|---|---|---|
| 0.0 - 0.4 | Distinct, countable echoes/slapback | A rhythmic accent; risks reading as a "clap"/discrete artifact if the source has any percussive transient |
| 0.5 - 0.75 | Audible repeating pattern, decays within a few seconds | Mid-song texture, still clearly "an echo" |
| 0.85 - 0.95 | Repeats blur into a near-continuous decaying wash | Ambient/soundscape beds, Frippertronics-style tape-loop textures — the repeats stop reading as discrete events |
| → 1.0 | Never meaningfully decays | Avoid outside a deliberate infinite drone; compounds fast if reprocessed (see gain-staging below) |

## Gain staging when cascading wet effects

`Delay` and `Reverb` add energy; nothing in the primitives normalizes it back down.
A single pass is usually fine, but **two or more cascaded wet passes — e.g.
reprocessing an already-rendered mix through the same `Delay`/`Reverb` chain again via
`chain()` (see `known-limitations.md`) — can silently exceed 1.0 amplitude.** Found in
practice: two passes of `feedback=0.9` delay with no normalization between them peaked
at 5.56 (should be ≤1.0), 33.8% of samples clipped. Digital clipping's harmonic
distortion is high-frequency-heavy, so it reads as harsh top-end distortion, easy to
mistake for "too much reverb" rather than an actual level problem.

No `normalize` primitive exists yet (tracked in
[issue #52](https://github.com/mewdev/recut-prototype/issues/52)). Until then, check
`np.abs(audio.samples).max()` after any multi-pass wet chain, especially with
`feedback > 0.7`, and peak-normalize manually if it's over ~0.9:

```python
def peak_normalize(audio, target_peak=0.85):
    peak = np.abs(audio.samples).max()
    if peak <= target_peak:
        return audio
    return Audio(audio.samples * (target_peak / peak), audio.sr)
```

## Chain ordering

```python
# Correct for a closing/exit effect on a clip:
fx=[FilterSweep(...), Reverb(...), Fade(vol_start=1.0, vol_end=0.0)]

# Wrong — fading first then adding reverb reintroduces level after the fade:
fx=[Fade(...), Reverb(...)]
```

**General rule:** static filter first, sweep/reverb/delay next, volume envelope (`Fade`) last. `Clip.fx` is a plain list applied in order — nothing enforces this for you, see `validation-workflow.md` for what *is* checked automatically.
