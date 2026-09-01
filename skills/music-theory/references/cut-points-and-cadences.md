# Cut Points and Cadences

A cadence is how a phrase ends harmonically — the punctuation that signals "concluded," "paused," "surprised," or "still moving." A candidate cut boundary that lands right after a strong cadence reads as a deliberate, clean edit. One that lands mid-tension reads as an accident. This file is about **classifying the cadence at an existing boundary**, not choosing one to compose.

Read chord data with `../assets/chord-notation.md` — the map stores `root:quality` strings (`C:maj7`), not lead-sheet notation.

## The three functional groups

Every chord pulls toward one of three roles. Knowing which role the chord just before a candidate cut plays tells you how "finished" it sounds:

- **Tonic (T)** — `I`, `vi`, `iii` (major) / `i`, `♭VI`, `♭III` (minor). Stable. An arrival, not a question.
- **Predominant (PD)** — `ii`, `IV`, `vi` (major) / `iiø`, `iv` (minor). Motion away from tonic, toward dominant.
- **Dominant (D)** — `V`, `vii°`. Maximum tension. `V` strongly wants `I` — the single strongest expectation in tonal music.

**A cut landing on a stable tonic chord is safe. A cut landing on (or right before resolving) a dominant chord is landing mid-tension** — the ear expects one more chord.

## Cadence types, strongest closure to weakest

| Cadence | Chords | Feeling | Cut-point read |
|---|---|---|---|
| **Perfect Authentic (PAC)** | `V → I`, root position | Maximum closure, "period" | Safest possible exit point |
| **Imperfect Authentic (IAC)** | `V → I`, inverted or non-root soprano | Closure, lighter, "comma" | Clean exit, slightly softer |
| **Plagal** ("amen") | `IV → I` | Gentle, rocking, no leading-tone pull | Good soft ending; common rock/gospel outro flavor |
| **Phrygian half (minor)** | `iv⁶ → V` | Bittersweet, archaic, strong pause | Reasonable pause point, not a true ending |
| **Half (HC)** | ends on `V` | "Question" — wants to continue | **Risky exit** — cutting here leaves the harmony hanging unless that open feeling is the intent |
| **Deceptive** | `V → vi` (or `♭VI`) | Surprise, "not done yet" | **Bad exit** — actively signals more is coming |
| **Elision / no cadence** | phrase runs into the next with no resolution | Continuous flow | **Not a cut point** — there's no natural gap here at all |

**Caveat**: pop songs often *avoid* PAC at internal section boundaries on purpose, to keep momentum forward — don't assume every verse→chorus boundary is "supposed to" resolve cleanly. A half cadence or deceptive cadence at an internal boundary is often correct songwriting, not a defect. It only becomes a problem if you're cutting there and expecting a clean stop.

## Practical detection from the map

For a candidate cut at time `t`, look at `EnrichedSegment.chords` entries ending at or just before `t`:

1. Take the chord active in the last ~1–2 seconds before `t`.
2. Classify its function (T/PD/D) against the segment's/song's `key` (`MusicMap.key.tonic`/`.mode`).
3. If it's dominant-functioning (`V`, `vii°`, or a `7` quality on the dominant root) and the *next* chord after `t` would have been tonic — you're cutting off a resolution. Either shift the cut a beat later (past the resolution) or accept the tension deliberately if the brief wants an unresolved/open ending.
4. If it's tonic-functioning, the cut point is harmonically safe regardless of exact timing.

## Modulation caveat

If the song modulates (a bridge that shifts key, or a "truck-driver" half-step-up final chorus), cutting into or out of that section without its harmonic setup can orphan a dominant-of-the-new-key chord — the listener hears a chord that doesn't resolve because the chord that was supposed to follow it belonged to a section you cut away. Check whether a candidate boundary sits inside a modulated passage before trusting a simple T/PD/D read; a brief chromatic passing chord (tonicization) is not the same as a real key change and doesn't carry this risk.

## Quick reference

| Need to... | Look for |
|---|---|
| Cut cleanly at the end of a section | Tonic chord, ideally after a PAC/IAC |
| Cut into a chorus/loud arrival | Cut right after the resolution lands, not on the dominant before it |
| Deliberately leave things open (e.g. a teaser/preview clip) | Half or deceptive cadence, or elision |
| Loop a section seamlessly | Cadence at the loop-back point should match the harmonic expectation at the loop start |
