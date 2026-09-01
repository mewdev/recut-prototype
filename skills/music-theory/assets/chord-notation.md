# Chord Notation — recut's format vs. lead-sheet/Roman numeral

recut's `EnrichedSegment.chords` (`ChordEntry.chord`, `src/recut/map/schema.py`) stores **MIREX-style `root:quality` strings**, validated against a 380-entry vocabulary (`_load_chord_vocab("full")`, `src/recut/map/data/full_chord_list.txt`) — **not** the `Cmaj7` lead-sheet notation used elsewhere in music theory. Translate before applying any theory content.

## Format

`ROOT:QUALITY`, where `ROOT` is a natural/sharp/flat letter name (`C`, `C#`, `Db`, ...) and `QUALITY` is a chord-quality suffix. `N` (no colon) means **no chord** — silence or unpitched material, not a rest to translate.

## Real examples from the vocabulary, translated

| recut (`root:quality`) | Lead-sheet | Roman numeral (if root is the key's tonic-relative degree, key = C major) |
|---|---|---|
| `C:maj` | `C` | `I` |
| `C:min` | `Cm` | `i` (if C is treated as tonic in a minor context) |
| `C:7` | `C7` | `I7` (or `V7` of the key a 5th below — check function, don't assume tonic) |
| `C:min7` | `Cm7` | `i7` / `vi7` depending on key context |
| `C:maj7` | `Cmaj7` | `IΔ` |
| `C:dim` | `Cdim` | `vii°`-shaped (function depends on scale degree) |
| `C:sus4` | `Csus4` | — (no standard Roman numeral; describe as "sus4 on \[degree\]") |
| `C:maj/5` | `C/G` (C major, 5th in bass — second inversion) | `I⁶⁄₄` |
| `C:min/b7` | `Cm/Bb` (♭7 scale-degree bass) | `i⁴³`-ish; treat as a bass-note-specified inversion |
| `N` | (no chord / silence) | — |

**Root only tells you the chord's letter name, not its function.** To get a Roman numeral you still need the song's key (`MusicMap.key.tonic`/`.mode`) and have to compute the root's scale degree relative to it — `C:maj` is `I` in C major but `IV` in G major.

## Reading a `chords` list for cadence detection

```
{"start": 41.2, "end": 42.8, "chord": "G:7"}
{"start": 42.8, "end": 45.0, "chord": "C:maj"}
```

In the key of C major, `G:7 → C:maj` is a dominant-seventh resolving to tonic — a **Perfect Authentic Cadence** if root position and the melody lands on scale-degree 1. See `../references/cut-points-and-cadences.md` for what to do with that classification.

## Common ambiguity — quality suffixes

Slash-style quality suffixes (`maj/5`, `min/b7`, `maj/b7`) encode **scale-degree bass notes relative to the chord's own root**, not the song's key — `C:maj/5` means "C major triad with its own 5th (G) in the bass," independent of what key the song is in. Don't confuse this with a Roman-numeral inversion figure, which is relative to the *key's* tonic.
