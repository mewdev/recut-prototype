# Todo & Ideas

## Pipeline fixes (post map-schema v3)

- [ ] **Key detection improvement** — current frequency heuristic (`detect_key`) picks most common chord root.
      Fails when dominant (V) chord appears more than tonic (e.g. "End of Beginning": A:maj > D:maj but key is D major).
      Fix: implement Krumhansl-Schmuckler algorithm or use `music21` key detection.
      Known limitation in v0.1 map output.

- [ ] **Time signature detection** — `modal_chordmini.py` hardcodes `"4/4"` (line 177).
      madmom's `DBNDownBeatTrackingProcessor` needs meter as input, doesn't detect it.
      Needs separate meter classifier (`RNNBarProcessor` + meter model).
      Required before processing waltz, 6/8, or odd-meter tracks.
      Block: implement after map schema v3 is settled.

## Map schema v3 — MUF-informed enhancements
*From MUF architecture analysis (2026-07-03). Priority order:*

- [ ] **Key field** — add `"key": {"tonic": "D", "mode": "major"}` to map output.
      ChordMini already computes chords; key = most common chord root + mode aggregated over song.
      Lowest effort of all enhancements.

- [ ] **Phrase-level segmentation** — add `"phrases": [t0, t1, t2, ...]` timestamps within each segment.
      Apple finds ~29 phrases on a 2:39 track (avg 5.1s = 8 beats at 80 BPM).
      Options: allin1 already outputs phrase boundaries — extract them into map. Or post-process segments by downbeat count.
      Critical for: LLM cutting decisions at sub-section granularity.

- [ ] **Instrument activity per segment** (not full stems) — `"instruments": {"vocal": 0.72, "bass": 0.68, "drums": 0.81, "other": 0.55}`.
      Derive from Demucs stems already computed: RMS per stem per segment → normalize 0–1.
      Apple's approach (10× lighter than Demucs) — we already have Demucs so activity is free.
      Use case: "cut where bass drops", "cut on a drum hit".

- [ ] **EBU R128 loudness** — add integrated LUFS to map metadata.
      `pip install pyloudnorm` → one call → `{"integrated": -9.61, "peak": -0.01}`.
      Use case: detect loudness mismatch between sections, normalize to streaming targets (-14 LUFS Spotify).

- [ ] **Pace / cut-rate field per segment** — `"pace_cuts_per_min": 20.0`.
      Apple derives from structure model (41-class, 0–80 cuts/min). Approximate: `60 / (beats_per_cut × bpm)`.
      Gives LLM a concrete "how dense should editing be here" signal.

- [ ] **Per-beat + downbeat timestamps** — currently have bar count per segment, not timestamped beats.
      madmom DBN already outputs these. Add `"beats": [...]` and `"downbeats": [...]` to map root.
      Apple outputs 211 beats + 53 downbeats for a 2:39 track.

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

- [ ] **Static edit validator** (issue #10) — lint for audio cuts. Checks edit plan against MusicMap before render: cut points inside segments, non-adjacent joins, key/energy mismatch. MVP = structural checks only (map-based). Perceptual checks (click detection, loudness jump) later. Runs as `plan.validate()` before `plan.render()`.
  - Q: How to ensure `compose()` is always written correctly? Runtime validation catches map-level mistakes (wrong labels, bad cut points). Static types (Pylance) catch wrong arg types. `Literal` typing for segment labels impractical with dynamic maps — runtime is right call for MVP.
## Pipeline
## Stems

- [ ] Extract stems from allin1 JSON output — write utility that reads `labour-allin1.json` and writes `testing/01/stems/{vocals,drums,bass,other}.wav`. No re-running needed, stems already computed by Demucs inside the Modal pipeline.
      Use case: feed isolated vocal stem into ending delay layer (instead of full mix) for cleaner echo tail.

- allin1 default Demucs model is fine for vocals, but other stems (drums, bass) could be higher quality with htdemucs or htdemucs_ft


## Documenting testing cases for cutting model traning:

- how to write training data which comes from documenting manual editing decisions — every intervention is a future training example. The reason field is the most important — it's where musical intelligence gets encoded.-