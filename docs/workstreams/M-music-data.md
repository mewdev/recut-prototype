# Workstream M: Richer music data (instrument activity, pace, key changes)

**Goal:** give the map, the linter and the cutting agent the signals they're missing
today:
- **Instrument activity** (`drum`, `bass`, `vocal`, `other`, 0–1 over time). Fixes the
  known gap in `LIMITATIONS.md`: "quiet but still has drums" vs. "actually sparse", which
  is why chorus exits sometimes fade badly. It also enables "don't cut mid-vocal".
- **Pace**: perceived energy/momentum over time, independent of BPM. A breakdown at
  high BPM reads as low pace.
- **Key ranges** (key changes) and **short-term loudness** over time.

**Model:** Apple's Music Understanding framework (macOS/iOS 27+, Swift) returns exactly
these (`InstrumentActivityResult` with drum/bass/vocal/other, `PaceResult`,
`KeyResult.ranges`, `LoudnessResult`, `StructureResult` with sections → segments →
phrases). It needs an Apple-silicon Mac, which the operator doesn't have yet (Intel Mac;
cloud Macs have a 24 h minimum rental). **Decision 2026-11-13:** build a cross-platform
version now on Modal, and add Apple MU later as a second source for the same fields (M4).

**Read first:** `AGENTS.md` → `src/analysis/pipeline.py` (Modal app `recut-analysis`) →
`src/recut/map/schema.py` / `make_map.py` → this file → `docs/STATUS.md`.
**Owns:** `src/analysis/`, `src/recut/map/`, `src/recut/analysis_client.py`.
**Suggested model:** Sonnet.

## M1: Stems + instrument activity (Modal, GPU)
- New Modal function `run_stems` in `pipeline.py`:
  - Demucs `htdemucs` (MIT) on a T4, timeout 600 s.
  - Returns 4 stems (drums, bass, vocals, other) as 44.1 kHz FLAC bytes **and**
    activity curves: per stem, RMS in 100 ms hops → dB → mapped to 0–1, where
    -50 dBFS = 0 and the stem's own 95th percentile = 1, smoothed over 300 ms.
  - Also returns detected ranges where activity > 0.25 for ≥ 1 bar.
- `analyze_raw` spawns it in parallel with the others.
- Stems are saved to `.appdata/tickets/<id>/stems/<source_id>/<stem>.flac` (week-2 mashups
  will use them); only the curves go into the map.
- Done when: a test with a mocked Modal function covers the curve maths, and the
  operator runs one real track and the curves look right in the GUI (M3).

## M2: Pace + key ranges + short-term loudness (CPU, no GPU)
- **Pace:** onset events per minute (librosa onset detection on the full mix) in 4 s
  windows, 1 s hop. Store raw events/min; also store a 0–1 version normalized per track.
- **Key ranges:** Essentia key extraction in 8-bar windows aligned to downbeats. Merge
  equal neighbours. Only report a change if it lasts ≥ 8 bars.
- **Short-term loudness:** pyloudnorm-style 3 s windows, 1 s hop, in LUFS.
- Can run locally inside `make_map` (CPU, a few seconds), except key, which reuses the
  Modal key image.

## M3: Map schema + use the data
- `MusicMap` gets **optional** fields, so old maps keep loading (M0 already added `bpm_raw`: the tempo
  estimator's value when it disagreed with the beat grid, which now defines `bpm`):
  ```
  instrument_activity: {drum|bass|vocal|other: {hop_s: 0.1, values: [...], ranges: [[start, end], ...]}}
  pace: {hop_s: 1.0, events_per_min: [...], normalized: [...]}
  key_ranges: [{start, end, tonic, mode}]
  loudness_short_term: {hop_s: 1.0, lufs: [...]}
  analysis_sources: {"instrument_activity": "demucs-htdemucs", "pace": "librosa-onsets", ...}
  ```
  Each `EnrichedSegment` also gets summaries: `drum_activity`, `vocal_activity` (means),
  and `pace` (mean normalized).
- **Linter rules** (with workstream Q / A9):
  - `ending_drums` (warn): the cut ends with a fade on a section where drum activity is
    > 0.6 in its last bar. This is the exact failure noted in LIMITATIONS.
  - `mid_vocal` (warn): a splice falls inside a vocal range, more than 1 beat from the
    range's edges.
  - `key_compat`: use `key_ranges` at the splice time instead of the global key.
- **GUI:** thin activity lanes (drum/bass/vocal) and a pace line under each source row,
  toggleable. These go in `src/recut/server/static/app.html`; coordinate via STATUS.
- **Cutting skill:** add to `skills/music-theory/references/exit-design.md` how to use
  activity and pace for exits and joins.

## M4 (later, needs an Apple-silicon Mac on macOS 27+): Apple Music Understanding
- `tools/mu-analyze/`: a Swift command-line tool. `mu-analyze <file>` runs
  `MusicUnderstandingSession(asset:).analyze()` and writes JSON in the **same shape** as
  M3's fields (activity 0–1 per instrument, pace, key ranges, loudness, structure).
- `recut.analysis_client` calls it over SSH or a small HTTP worker on that Mac when
  `RECUT_MU_HOST` is set.
- Store as a second source (`analysis_sources.*: "apple-mu"`). The GUI can compare
  Demucs and Apple curves, which gives a free accuracy check.
