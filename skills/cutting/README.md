# Cutting Skills

Decision rules for audio editing agents. Read these before executing any cut.
Each document is a rule set with the "why" attached — not a tutorial.

## Order of Operations

1. **[prompt-disambiguation.md](prompt-disambiguation.md)** — resolve intent before touching anything
2. **[map-interpretation.md](map-interpretation.md)** — what the music map tells you and what it doesn't
3. **[stem-handling.md](stem-handling.md)** — additive timeline rules, taper strategy, bleed detection
4. **[effects-routing.md](effects-routing.md)** — which primitives work on which source types
5. **[transitions.md](transitions.md)** — stagger rules, masking, clean joins
6. **[exit-design.md](exit-design.md)** — fade timing, sweep parameters, reverb settings

## Key Rules (the short version)

- **Disambiguate first.** "From 1:01" has two valid interpretations. Ask before cutting.
- **Snap to downbeats.** Always. No exceptions.
- **Single timeline, additive mixing.** Never `xfade_join` time-aligned stems.
- **`filter_sweep` = sustained pitched sources only.** Kicks + IIR filter = resonance clicks.
- **Fade drums to zero 2 bars BEFORE the silence zone.** Transients bypass masking.
- **Reverb chain order:** EQ → reverb → fade. Never reverb → reverb.
- **Fade = last 25% of exit section.** The listener needs to hear the final chord.
- **The simplest edit (V2) is often correct.** Creative exits add value only when the user asks.

## Provenance

Derived from the chicago.mp3 cutting session (testing/02), versions v1–v16.
16 iterations, covering: timing, stem isolation, IIR artifacts, masking, reverb routing.
