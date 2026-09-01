# Transitions and Masking

Why cuts click, and how to avoid it. This is perceptual/signal-processing knowledge, independent of the recut API — it applies to the one full-mix signal `compose()` works with today (see `known-limitations.md`; there's no live stem removal to reason about yet, so read "instrument" below as "content within the mix," not a separable file).

## The masking problem

**Temporal masking:** a loud transient (a kick hit, a hard downbeat) suppresses perception of other co-timed transients for tens of milliseconds. When level drops sharply right after such a transient (e.g. a `Fade` starting immediately after a beat), whatever the ear couldn't hear a moment ago becomes the loudest thing in the room.

**Spectral masking:** a loud low-mid element raises the audibility threshold across nearby frequencies. A section that's dense and full in the low end can hide content that becomes exposed the instant that section fades or the mix thins out later in the same clip.

**Checklist before applying an effect that changes level or frequency content mid-clip:**
1. What's the loudest transient near the point the effect takes hold? (`EnrichedSegment.loudness_db_start`/`_end` is your best available signal.)
2. Will the effect's own onset (e.g. a `FilterSweep` starting at an audible cutoff) itself read as a transient — a "room switch" click?

## Taper timing rule

**A fade should reach zero *before* the next audible transient, not at it.** A linear fade ending exactly on beat N still has non-trivial amplitude on the beat(s) immediately before N — percussive content at 5–12% amplitude bypasses masking and reads as a click in an otherwise quiet mix.

**Rule of thumb:** if a section must be effectively silent by a given downbeat, end the `Fade` (or the `Clip`'s extent) a bar or two before that downbeat, not on it.

## Stagger rule for multi-step transitions

When a cut moves through several distinct textures in sequence (e.g. full mix → sparse section → tag ending), don't collapse every change onto one boundary — a single instant where "everything changes at once" reads as the track switching off rather than evolving. Spread level/effect changes across a few bars so each change has room to register before the next.

## Avoiding a click at effect onset

Starting `FilterSweep` at an audible cutoff (e.g. `freq_start=8000` for a `low` sweep) on a signal that's currently loud creates an instant, audible spectral step.

**In order of preference:**
1. **Transparent start** — begin the sweep near the edge of the audible range (`freq_start=18000` for `low`, or `freq_start` very low for `high`) with `curve > 1` so the filter is inaudible at t=0 and only becomes apparent later.
2. **Cross into the effect** — end the dry `Clip` with a short `Fade` out while the next, effected `Clip` fades in (use an `XFade` between them, or manually overlap two `Clip`s' `fx`), so the ear hears a blend rather than a switch.
3. **Start the effect in a quieter moment** — apply it from a point where the signal is already lower-level, so the filter's own initialization has less to react to.
