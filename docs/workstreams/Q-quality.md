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
Rule names are prefixed `qc_`.

**Backends (decision 2026-11-13: the prototype is non-commercial, so Essentia (AGPL) is
allowed):**
- **Essentia** (`pip install essentia`) is the primary detector. Prebuilt wheels
  (checked 2026-11-13): Intel macOS py3.10–3.11, Apple Silicon py3.10–3.12, Linux x86_64
  incl. py3.13. Use Python 3.10 or 3.11 for the `recut` env to cover all of them. It for clicks, discontinuities, saturation and gaps. Use
  `ClickDetector`, `DiscontinuityDetector`, `SaturationDetector` and `GapsDetector` on
  runs on frames of the mono render. Report each hit with its time and the nearest splice id
  (within 50 ms).
- **pyloudnorm (MIT) + numpy/scipy** for loudness/true peak and the splice-relative
  checks (`qc_gain_jump`, `qc_tilt_jump`), and as the **fallback** when `import essentia`
  fails. In that case the hand-written versions in the table below run, plus one `info`
  issue `qc_backend: essentia not installed, using basic detectors`.
- Keep every Essentia call inside `src/recut/qc_essentia.py` behind the
  `RECUT_QC_ESSENTIA` switch (default on). Before any commercial launch, that file gets
  removed or replaced. Add `essentia` as an optional extra: `pip install -e ".[qc]"`.

| rule | how | default threshold |
|---|---|---|
| `qc_loudness` | integrated LUFS (pyloudnorm) | warn outside −16…−9 LUFS |
| `qc_limiting` | replaces the engine's `peak_clip`: maximum limiter gain reduction (pre-master peak minus output peak, measured in 50 ms windows) | warn > 3 dB (audible squash). `peak_clip` fires on nearly every reverb wash over mastered sources, so it's noise. |
| `qc_true_peak` | peak of a 4× oversampled signal (`scipy.signal.resample_poly`) | warn > −1.0 dBTP |
| `qc_clipping` | Essentia `SaturationDetector`; fallback: runs of ≥ 3 consecutive samples with \|x\| ≥ 0.999 | error if any |
| `qc_click` | Essentia `ClickDetector` + `DiscontinuityDetector` over the whole file; fallback: for each splice, high-passed (> 4 kHz) energy in ±10 ms vs. the median of ten 20 ms windows around it | warn (fallback: > 4×, ≈ +6 dB). Hits within 50 ms of a splice name the splice. |
| `qc_gain_jump` | momentary loudness (400 ms) just before vs. just after each splice | warn > 3 LU |
| `qc_gap` | Essentia `GapsDetector`; fallback: RMS < −60 dBFS for > 200 ms. Either way, ignore the very start/end and deliberate `fade_out`s | warn |
| `qc_bandwidth` | per **source**: the frequency above which energy drops 40 dB below the median spectrum level | info < 15 kHz ("low-quality source") |
| `qc_tilt_jump` | spectral centroid in 1 s windows either side of a splice | warn if the ratio > 1.6 (EQ/brightness mismatch) |
| `qc_dc` / `qc_phase` | mean offset; L/R correlation over the whole file | warn \|DC\| > 0.01; warn correlation < 0 |

- Each check stays under ~50 ms on a 3-minute track (the live preview depends on it).
- `render.json` gains `qc: {lufs, true_peak_dbtp, ...}` as **extra info**. If a contract
  field is needed, log a Blocker instead of editing `src/recut/contracts/`.
- Tests must pass **with and without** Essentia installed (skip the Essentia-specific
  assertions via `pytest.importorskip("essentia")`).
- Done when: each rule has a test with synthetic audio (an injected click, a −20 dB gap,
  a clipped run, a low-passed source), and the demo ticket's renders produce no `qc_*`
  error.

## Before any commercial use
Essentia (AGPL, and network use counts) has to go. Remove `qc_essentia.py` or replace it
with permissively licensed detectors, and tune the fallback thresholds with the review
data collected by then. The same applies to Essentia key detection and MuQ in the
analysis pipeline (README).
