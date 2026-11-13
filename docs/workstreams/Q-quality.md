# Workstream Q — Automatic checks: musical linter (A9) + audio QC (Q1)

Two automatic checks that catch obvious problems before the operator listens. Both
write into `render.json.issues`, so they show up in the GUI's Problems list and in
`recut report`.

- **Linter**: runs before rendering, on plan + music map. "Is this a musically sensible
  cut?"
- **QC**: runs after rendering, on the audio. "Is the rendered file technically clean?"

Every splice the operator marks bad that neither check flagged shows up in
`recut report` as a "validator miss". Those misses are the input for new rules
(`docs/IMPROVEMENT_LOOP.md`). Thresholds start as the defaults below and get tuned from
review tags:
- tagged `artifact` but QC passed → the threshold is too loose
- flagged, but the operator keeps marking it ok → too strict

**Read first:** `AGENTS.md` → `docs/PLAN.md` §3.3 → this file → `docs/STATUS.md`.
**Suggested model:** Sonnet. Do this after A7/A8 (it touches `engine.py`).

## A9 — Musical linter rules (`src/recut/validator/`, called from `engine.py`)
Issue severity is `warn` unless noted. Each rule: one passing and one failing test.

| rule | condition |
|---|---|
| `phrase_align` | a splice point isn't on a 4- or 8-bar phrase boundary (map `phrases`, tolerance 30 ms) in the outgoing **or** incoming source |
| `ending` | the last clip doesn't end at a section end or the song's real end, and has no `fade_out` |
| `energy_drop` | loudness drops more than 6 dB from one clip to the next (map `loudness_db_end` → `loudness_db_start`) without a fade or xfade |
| `duration` | already in the engine; move it here: \|duration − target\| > 2 s → warn, > 10 % → error |

## Q1 — Audio QC (`src/recut/qc.py`; the engine calls `run_qc(audio, info) -> list[Issue]`)
Use pyloudnorm (MIT) + numpy/scipy. **Don't use Essentia in this module** (it's AGPL,
see README). Rule names are prefixed `qc_`.

| rule | how | default threshold |
|---|---|---|
| `qc_loudness` | integrated LUFS (pyloudnorm) | warn outside −16…−9 LUFS |
| `qc_true_peak` | peak of a 4× oversampled signal (`scipy.signal.resample_poly`) | warn > −1.0 dBTP |
| `qc_clipping` | runs of ≥ 3 consecutive samples with \|x\| ≥ 0.999 | error if any |
| `qc_click` | for each splice: high-passed (> 4 kHz) energy in ±10 ms vs. the median of ten 20 ms windows around it | warn > 4× (≈ +6 dB) |
| `qc_gain_jump` | momentary loudness (400 ms) just before vs. just after each splice | warn > 3 LU |
| `qc_gap` | RMS < −60 dBFS for > 200 ms, except at the very start/end and inside a deliberate `fade_out` | warn |
| `qc_bandwidth` | per **source**: the frequency above which energy drops 40 dB below the median spectrum level | info < 15 kHz ("low-quality source") |
| `qc_tilt_jump` | spectral centroid in 1 s windows either side of a splice | warn if the ratio > 1.6 (EQ/brightness mismatch) |
| `qc_dc` / `qc_phase` | mean offset; L/R correlation over the whole file | warn \|DC\| > 0.01; warn correlation < 0 |

- Each check stays under ~50 ms on a 3-minute track (the live preview depends on it).
- `render.json` gains `qc: {lufs, true_peak_dbtp, ...}` as **extra info**. If a contract
  field is needed, log a Blocker instead of editing `src/recut/contracts/`.
- Done when: each rule has a test with synthetic audio (an injected click, a −20 dB gap,
  a clipped run, a low-passed source), and the demo ticket's renders produce no `qc_*`
  error.

## Optional, later
Cross-check with Essentia's ClickDetector / DiscontinuityDetector / SaturationDetector /
GapsDetector inside the Modal analysis container (Essentia is already there), only while
tuning thresholds, and not in the hosted product until the license question is settled.
