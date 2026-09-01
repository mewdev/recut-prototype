# Known Limitations

## Cutting mechanics (`skills/cutting/references/known-limitations.md`)

- **No `eq` primitive** — static filtering only via `FilterSweep(freq_start=freq_end)`.
- **No partial-clip effect application** — every effect applies to a clip's entire
  buffer; "fade just the last 4 bars" needs two `Clip()` calls, not one parameter.
  [Issue #53](https://github.com/mewdev/recut-prototype/issues/53).
- **No live per-instrument/stem editing** — `compose()` takes one full-mix `Audio`.
  `Clip.source` exists as a field but isn't read at render time.
- **No bridge between `Clip`/`compose()` and raw `chain()` reprocessing**, and no
  gain-staging primitive — cascading wet `Reverb`/`Delay` passes can clip with nothing
  to catch it. [Issue #52](https://github.com/mewdev/recut-prototype/issues/52).
- **Validator is 3 structural rules, not a musical linter** — `label_exists`,
  `duration_exceeds`, `sequence_boundaries` only. No key/energy/rhythm-aware checks.
- Thin test coverage on `filter_sweep`/`reverb`/`delay`; `compose()` only tested
  indirectly.

## Musical judgment (`skills/music-theory/references/known-limitations.md`)

- **No harmonic function or cadence data in the map** — `ChordEntry` is `start/end/
  chord` only (a raw `root:quality` string). Cadence classification and tonic/
  predominant/dominant judgment are inferred by whoever's reasoning about the cut, not
  looked up or verified.
- **No sub-phrase repeat detection** — `phrases` is timestamps only, nothing marks a
  literal repeat.
- **No per-instrument/vocal activity signal** — same root cause as the cutting-side
  limitation above. Concretely bit us once: `exit-design.md` ranks `chorus` as the best
  exit zone by energy, but a chorus with full drums often fades unnaturally versus an
  already drum-sparse section — the map can't tell "quiet but still has drums" from
  "quiet and actually sparse."
- Chord and segment timestamps come from different models and can be mismatched by up
  to a few hundred ms at boundaries.

## Analysis pipeline / Modal

- **Fixed per-stage timeouts** (`src/analysis/pipeline.py`): beats 300s, key 180s,
  chords 600s, structure 300s (on a T4 GPU), 1200s overall — implies a practical
  track-length ceiling, and the structure stage isn't free-tier-friendly at scale.
- **Meter detection covers 3/4 and 4/4 only** — `DBNDownBeatTrackingProcessor(beats_per_bar=[3, 4])`
  tests both hypotheses and picks the best fit; it doesn't consider other meters
  (5/4, 6/8, 7/8, ...), so an odd-meter track gets forced into whichever of 3/4 or 4/4
  the model fits best, not detected accurately.
- Roman-numeral/harmonic-function chord fields, phrase-level sub-segmentation, and
  per-instrument activity (above) are all map-schema gaps, not skill-reasoning gaps —
  fixing them is an analysis-pipeline change, not a skill-doc change.

## Licensing

- **MuQ (SongFormer's audio encoder) is CC BY-NC 4.0 — non-commercial only.** This
  makes the structure-detection stage of the pipeline non-commercial as shipped.
  Replace MuQ with a MIT-licensed alternative (MERT, EnCodec) before any commercial
  use.
- **Essentia (key detection) is AGPLv3** — free for non-commercial use, a separate
  commercial license is required otherwise. AGPL's copyleft extends to network/SaaS
  use, not just redistribution — a stronger constraint than MuQ's clause above.
  Replace with a permissively-licensed key-detection method before any commercial or
  hosted use.
- See `README.md`'s model table for the full license breakdown — madmom,
  Chord-CNN-LSTM, SongFormer itself, and MusicFM are all permissively licensed.
