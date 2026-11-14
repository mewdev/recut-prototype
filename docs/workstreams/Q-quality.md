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

## Q0 — Intake check: block poor-quality uploads before analysis
`src/recut/intake.py`: `check_audio(path) -> IntakeResult{ok, problems: [{code, message}], info}`.
It must take under 1 s for a 5-minute file, because it runs while the client waits.

**Policy (updated 2026-11-14: the operator creates every ticket; clients never upload).**
The check **warns the operator**; it doesn't talk to clients. `recut ticket new` (and `/new`)
prints the problems in plain words and asks for `--override` on blocking ones, so the operator
can ask the client for a better file first.
- Accepted: lossless (WAV/FLAC/AIFF), MP3 ≥ 256 kbps, AAC/M4A ≥ 256 kbps.
- **The bitrate in the file can lie** (a 128 kbps MP3 re-saved as 320). Always also
  measure the **real bandwidth**: the highest frequency where the long-term spectrum is
  within 40 dB of its median level, using 30 s from the middle of the track.

| code | condition | message to the operator (plain words; can be forwarded to the client) |
|---|---|---|
| `undecodable` | ffprobe/decoding fails | "We couldn't read this file. Please export it again." |
| `low_bitrate` | lossy with a bitrate below 256 kbps (from ffprobe) | "This is a {n} kbps file. Please send WAV/FLAC, or an MP3/AAC of at least 256 kbps." |
| `low_bandwidth` | real bandwidth < 18 kHz, **whatever the container** (catches fake 320 and MP3-to-WAV) | "This file sounds like it came from a low-quality MP3 (nothing above {f} kHz). Do you have the original?" |
| `low_samplerate` | < 44.1 kHz | … |
| `too_short` / `too_long` | < 20 s or > 15 min | … |
| `fake_stereo` (info) | L = R (correlation > 0.999) | not blocking |
| `clipped_source` (info) | Essentia SaturationDetector / fallback clip runs | not blocking: shown to the operator only |

- `recut ticket new` and `POST /api/tickets` (operator-only) run the check on every file.
  Blocking problems → refuse without `--override` (CLI) or an "Upload anyway" checkbox
  (`/new`). The override and the problems are recorded in `request.json` (a new optional
  field; log a Blocker if the contract needs it) and in the ticket timeline.
- CLI: `recut check-audio <files>` prints the same result.
- Real music can legitimately have no high frequencies (lo-fi, old recordings), which is
  why the override exists. Thresholds get tuned from overrides that turn out fine.
- Done when: tests with synthetic files (white noise low-passed at 15 kHz saved as WAV
  → `low_bandwidth`; a 128 kbps MP3 made with ffmpeg → `low_bitrate`; a clean 44.1 kHz
  WAV → ok) pass, and the `/new` flow is checked in a browser.
- Model: Sonnet.

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
| `qc_loudness` | integrated LUFS (pyloudnorm) of the render vs the **sources it uses** (the used source ranges, concatenated per source). Absolute numbers stay in `render.json.qc`: `lufs`, `source_lufs`, `lufs_vs_source` | warn if the cut is > 1 LU louder than the loudest source used, or > 3 LU quieter than the duration-weighted mean of the sources (unintended level drop). Only without any source to compare (direct `run_qc` calls): the old absolute window −16…−9 LUFS. A loud master (−8 LUFS) is not a defect in itself (ticket 20261113-mbyv: every render warned) |
| `qc_limiting` | replaces the engine's `peak_clip`: maximum limiter gain reduction (pre-master peak minus output peak, measured in 50 ms windows) | warn > 3 dB (audible squash). `peak_clip` fires on nearly every reverb wash over mastered sources, so it's noise. The master limiter's static true-peak trim (`qc.true_peak_trim_db`) is discounted: it is a level offset, not squash. |
| `qc_true_peak` | peak of a 4× oversampled signal (`scipy.signal.resample_poly`) | warn > −1.0 dBTP. The master `limiter` is true-peak aware (Q2b, below), so on a limited render this only fires if something after the limiter raises the level |
| `qc_clipping` | Essentia `SaturationDetector`; fallback: runs of ≥ 3 consecutive samples with \|x\| ≥ 0.999 | error if any |
| `qc_click` | Essentia `ClickDetector` + `DiscontinuityDetector` over the whole file; fallback: for each splice, high-passed (> 4 kHz) energy in ±10 ms vs. the median of ten 20 ms windows around it | warn (fallback: > 4×, ≈ +6 dB). Hits within 50 ms of a splice name the splice. |
| `qc_gain_jump` | momentary loudness (400 ms) just before vs. just after each splice | warn > 3 LU |
| `qc_gap` | Essentia `GapsDetector`; fallback: RMS < −60 dBFS for > 200 ms. Either way, ignore the very start/end and deliberate `fade_out`s | warn |
| `qc_bandwidth` | per **source**: the frequency above which energy drops 40 dB below the median spectrum level | info < 15 kHz ("low-quality source") |
| `qc_tilt_jump` | spectral centroid in 1 s windows either side of a splice | warn if the ratio > 1.6 (EQ/brightness mismatch) |
| `qc_dc` / `qc_phase` | mean offset; L/R correlation over the whole file | warn \|DC\| > 0.01; warn correlation < 0 |

### Q2b — true-peak-aware master limiter (`devices.limit`)
Decision (2026-11-13): pedalboard's Limiter holds the **sample** peak at the ceiling, and on a
loud master the 4× oversampled peak then sits 0.2 to 1 dB above it (demo: +0.06 dBTP at a −1 dB
ceiling), so `qc_true_peak` fired on every limited render. After limiting, the limiter measures
the 4× true peak (`qc.true_peak`, `top=50000` candidate maxima) and, when it is over the ceiling
(−0.01 dB margin), applies **one static gain trim** that puts it at the ceiling. Why static and
not an oversampled look-ahead limiter or a lower internal ceiling: it is exact for every track
(a fixed −1.5 dB ceiling either over- or under-corrects), costs one oversampling pass, and a
whole-render offset of about 1 dB is inaudible; the price is that the sample peak sits that much
under the ceiling. The trim is recorded in `Ctx.trim_db` / `render.json.qc.true_peak_trim_db` and
is discounted by `qc_limiting`. A limiter whose sample peaks are already under the ceiling but
whose true peak is over it is trimmed too.

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
