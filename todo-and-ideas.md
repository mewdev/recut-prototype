# Todo & Ideas

## Analysis

- [ ] Vocal position detection — detect where vocals are present/absent in a track.
      Needed for: smarter fade-out placement (avoid cutting mid-phrase/mid-word),
      better cut point selection, section labeling refinement.
      Tools to explore: pyannote.audio, Demucs vocal stem + energy envelope.

- [ ] Cadence detection — currently `cadences: []` in the map. This is the primary "safe cut point" signal.
      A perfect cadence = harmonic resolution = clean place to cut without tension.
      Needed for: tier-2 primitives (borrowEndingCadence, crossfadeAtHarmonicNeutralPoint).

- [ ] Roman numeral + harmonic function — chord fields `roman` and `function` are empty.
      Have raw chords (Bm, Em, F#) but not harmonic roles (i, iv, V).
      Needed for: reasoning about whether a cut lands on tension or resolution.

- [ ] Phrase boundaries — within a section (e.g. 30s verse) there are no 4-bar/8-bar phrase markers.
      Currently only have section-level and beat-level granularity — nothing in between.
      Needed for: cuts that respect phrase structure, not just section boundaries.

- [ ] Energy curve — no per-beat or per-segment loudness/density signal.
      Needed for: detecting builds/drops, smarter fade placement, section labeling refinement.

- [ ] Segment label accuracy — allin1 labels first segment as "verse" (should be "intro"),
      and section boundaries are approximate (chorus detected at 54.7s, actual downbeat at 51.15s).
      Consider: post-processing pass to correct intro/outro labels + snap boundaries to nearest downbeat.

## Primitives

- [ ] **LLM2Fx integration** — Sony Research paper (arXiv 2505.20770 + 2512.01559, GitHub: SonyResearch/LLM2Fx).
      Two systems:
      - LLM2Fx v1: natural language → EQ/reverb parameters (text-to-parameter)
      - LLM2Fx-Tools v2: reference audio pair → effect chain with CoT reasoning (style transfer)
      Relevance: when user describes a creative effect in natural language ("warm church reverb", "underwater feel"),
      LLM2Fx predicts the parameters → feeds directly into our existing `chain()` primitives.
      Integration point: `chain(audio, sr, (llm_fx_from_text, {"prompt": instruction}), ...)`
      Also: LP-Fx dataset (101K instruction→effect chain examples) could augment training data for the cutting model.
      Limitation: currently only EQ + reverb; GPT-4o works best for parameter prediction.
## Editing
## Pipeline
## Stems

- [ ] Extract stems from allin1 JSON output — write utility that reads `labour-allin1.json` and writes `testing/01/stems/{vocals,drums,bass,other}.wav`. No re-running needed, stems already computed by Demucs inside the Modal pipeline.
      Use case: feed isolated vocal stem into ending delay layer (instead of full mix) for cleaner echo tail.

- allin1 default Demucs model is fine for vocals, but other stems (drums, bass) could be higher quality with htdemucs or htdemucs_ft


## Documenting testing cases for cutting model traning:

- how to write training data which comes from documenting manual editing decisions — every intervention is a future training example. The reason field is the most important — it's where musical intelligence gets encoded.-