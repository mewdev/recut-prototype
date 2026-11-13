# Build Status / Handoff Log

**Every agent reads this file before starting and updates it before ending.** It is the
only memory shared between agent sessions. If something isn't written here, the next
agent won't know it.

## Rules
1. When you start a task: set its row to `in_progress` with your workstream letter.
2. When you finish: set it to `done` and add a Log entry (newest at the top).
3. If you're blocked or unsure about a contract, **don't guess**. Add a *Blockers* entry,
   leave the task as `blocked`, and move to the next task you can do.
4. If you made a decision the contracts didn't cover, add it under *Decisions* with one
   line on why.
5. Keep entries short: what changed, files touched, the command that proves it works.

## Tasks

| Task | Status | Notes |
|---|---|---|
| D1 contracts (`src/recut/contracts/`) + fixture ticket | done | units parser, plan/render/ticket models; demo ticket = `recut ticket demo` |
| A1 plan v2 loader | done | pydantic `Plan` in contracts (strict: unknown fields are errors) |
| A2 multi-source compose | done | `src/recut/engine.py` (timeline, not concatenation) |
| A3 LUFS match | todo | |
| A4 render.json | done | `engine.render_plan` → `RenderInfo` |
| A5 cross-song validator rules | todo | |
| A6 session logging | partial | the server/CLI log renders + reviews to `events.jsonl`; `RECUT_SESSION` for direct `compose()` calls is still todo |
| A7 timeline engine: tracks, joins, returns/sends, master | done | `engine.py`, `devices.py` (reverb + limiter), `automation.py` (gain/send ramps + points). Tests: `tests/engine/test_timeline.py` |
| A8 devices, automation, old-format adapter, skill docs | done | `devices.py`, `automation.py`, `legacy.py`; skill docs + README rewritten. Tests: `tests/engine/test_devices.py`, `test_legacy.py`, `test_ending_transplant_doc.py` |
| B1 ticket store | done | `src/recut/tickets.py` |
| B2 FastAPI app | done (no share routes) | `src/recut/server/app.py`, `recut serve` |
| B3 SSE live reload | done | polling, renders stale iterations |
| B4 waveform peaks | done | on request, cached in memory |
| B5 share links | todo | |
| B6 CLI + transcript hook | partial | CLI done; hook todo (put it in `scripts/hooks/`) |
| B7 `recut report` | todo | Haiku; needed by day 7 |
| B8 Docker image | todo | Haiku, after A8. Intel Mac / Arch / VPS from one image |
| Q0 intake check (block low-quality uploads) | todo | Sonnet; docs/workstreams/Q-quality.md |
| A9 musical linter rules | done | `src/recut/validator/linter.py` (`lint_plan`, called from `engine.render_plan`); tests `tests/validator/test_linter.py` |
| Q1 audio QC after render | done | `src/recut/qc.py` (+ `qc_essentia.py`, switch `RECUT_QC_ESSENTIA`); engine calls `run_qc`; tests `tests/engine/test_qc.py` |
| M1 stems + instrument activity (Demucs on Modal) | todo | Sonnet; docs/workstreams/M-music-data.md |
| M2 pace + key ranges + short-term loudness | todo | Sonnet |
| M3 map schema fields + linter rules + GUI lanes | todo | Sonnet, after M1/M2 |
| M4 Apple Music Understanding (Swift CLI) | later | needs an Apple-silicon Mac on macOS 27+ |
| C1 scaffold | todo | |
| C2 ticket list/page | todo | |
| C3 composition view | todo | |
| C4 source map | todo | |
| C5 A/B + live reload | todo | |
| C6 review panel | todo | |
| C7 client pages | todo | |
| I1 integration + real tickets | todo | Day 6–7, strongest model |

## Blockers
- Music maps can contain `NaN` loudness (zero-length segments), which isn't valid JSON for
  browsers. The server works around it (`/api/tickets/{id}/maps/{sid}`), but `make_map`
  should not produce NaN (analysis code, operator's call).

## Decisions
- 2026-11-13 — Q1: the frozen `RenderInfo` has no `qc` field, so the engine returns
  `recut.qc.RenderInfoQC` (a subclass with `qc: dict`); `render.json` carries it and readers
  that validate with `RenderInfo` ignore it. No contract edit, no blocker.
- 2026-11-13 — Q1: loudness uses pyloudnorm's K-weighting filters but evaluates them per 100 ms
  block in the frequency domain (within 0.01 LU of `Meter.integrated_loudness`, ~6x faster: that
  one takes 0.55 s per 3 min). True peak oversamples only around the 800 largest local maxima
  (checked against full 4x oversampling in a test).
- 2026-11-13 — Q1: click checks look only where a step can exist: a hard cut, or a `hold` xfade
  side. A cut that is contiguous in one source (the song plays on) or a smooth ramp is skipped:
  the downbeat onset there triggered the HF-energy rule (+6 dB) every time. Essentia hits away
  from such splices are one `info` `qc_click` ("click-like transients"), not warnings: on the
  demo they are the source's own hi-hat/sample transients (7 hits, identical in both renders).
- 2026-11-13 — Q1: `qc_bandwidth` reference level is the median of 100 Hz-8 kHz (not the median of
  all bins: a band-limited source pulls that median down and reads too wide).
- 2026-11-13 — Linter (A9): the map's `phrases` are 2-bar groups (`phrase_in`), so `phrase_align`
  accepts any map phrase start or section edge rather than strictly 4/8 bars. Loudness uses the
  section's `loudness_db_end`/`_start` only when the clip reaches that edge, else the section
  mean. An xfade shorter than 100 ms doesn't count as smoothing for `energy_drop`.
- 2026-11-13 — Upload quality: block, then ask for a better file (with an override).
  Accepted: lossless, MP3/AAC ≥ 256 kbps, and real bandwidth ≥ 18 kHz whatever the
  bitrate says (Q0).
- 2026-11-13 — Richer music data: Demucs stems + onsets on Modal now (M1–M3). Apple Music
  Understanding later as a second source; it needs macOS 27 on Apple silicon, and the
  operator's Mac is Intel.
- 2026-11-13 — `effects-cheatsheet.md` stays in `skills/cutting/assets/` (SKILL.md and the
  link checker already point there); the A8 brief said `references/`.
- 2026-11-13 — Not built: a Python builder API that mirrors the JSON (`Clip(..., sends=...)`,
  `Fade("2 bars", "exp")`). The name `Fade` is taken by the deprecated effect class, and the
  plan JSON is the source of truth for agents. Say if you want it.
- 2026-11-13 — Legacy adapter (`recut.legacy`): plain concat and `XFade` are sample-identical to
  `compose()` (tests, 1e-6). `Fade`/`Reverb`/`ReverbSweep`/`Delay`/`FilterSweep` convert to
  musically equivalent v2 features, not sample-identical (reverb tails now ring past the clip).
  Only the first `Fade` per clip is kept (reported in `LegacyPlan.warnings`). `recut render` (old
  CLI) still uses `compose()`; it was not switched over.
- 2026-11-13 — Reverb `size` is folded into `decay` (x0.7..x1.3); `eq` cuts are two cascaded
  first-order filters (12 dB/oct); delay filters sit in the feedback loop; auto_filter is a 12 dB
  ladder filter with `resonance` scaled 0..1.25 -> 0..1.
- 2026-11-13 — Level automation (`gain`, `sends.*`, volume) interpolates in the linear gain
  domain with the shape warping progress, so `-inf → 0` + `exp` swells from silence. Before a
  ramp starts the curve holds its `from`, after it ends its `to`; automation overrides the
  static `gain`/send value. Sends are post-fader (after clip gain, fades, xfade ramps).
- 2026-11-13 — The Freeverb `reverb` device: `decay` → room_size via a measured table
  (`devices.REVERB_DECAY_TABLE`, 0.53–9.5 s), `size` scales decay (x0.7…x1.3), the wet signal
  is level-compensated so `dry_wet: 100` is about as loud as the input.
- 2026-11-13 — Legacy xfade path: `render_plan(..., _legacy_xfades={node_id: (ms, curve)})`
  is an internal argument (not in the contract) that reproduces the old overlap length and
  old curves, including `qsin` out = `1 - sin`. Only `recut.legacy` (A8) should pass it.
- 2026-11-13 — Thin slice first (operator's request): D1 + engine + tickets + server + a
  no-build page, so the operator can pull and test before the workstreams fill in.
- 2026-11-13 — Renders are `audio.wav` (fast, lossless); mp3 only for client share links later.
- 2026-11-13 — The master `limiter` scales the output to `ceiling`: pedalboard's Limiter
  normalizes to 0 dBFS on its own.
- 2026-11-13 — The old `xfade` `qsin` fade-out is `1 - sin` (equal-gain), not `cos`
  (equal-power). The new engine's `equal_power` is real equal power. The A8 old-format
  adapter must keep the old curve to reproduce saved compositions exactly.
- 2026-11-13 — Merged `fix/song-edge-snapping` (the last segment runs to the end of the
  audio). The bundled `summer-party` map predates the fix: its last ~5 s (the fade-out)
  sit in a zero-length `silence` segment and can't be used until the map is regenerated.

## Log
- 2026-11-13 — Q1 done. `qc.run_qc(audio, info, pre_master=, sources=, fade_outs=)` runs at the end of
  `render_plan`; rules `qc_loudness`, `qc_limiting` (replaces `peak_clip`, removed), `qc_true_peak`,
  `qc_clipping` (error), `qc_click`, `qc_gain_jump`, `qc_gap`, `qc_bandwidth` (info), `qc_tilt_jump`,
  `qc_dc`, `qc_phase`, plus `qc_backend` (info) when essentia is missing. Numbers go to
  `render.json` under `qc` (incl. `timings_ms`). 210 tests pass with and without essentia
  (`RECUT_QC_ESSENTIA=0`, and with the package uninstalled). Demo renders: no `qc_*` error.
  Timing on a 3-min track: ~250-300 ms for the basic checks together, Essentia adds ~3.5 s.
- 2026-11-13 — A9 done. `validator/linter.py`: `phrase_align` (splice point within 30 ms of a map
  phrase or section edge, outgoing and incoming source), `ending` (last clip stops mid-section
  with no `fade_out`), `energy_drop` (> 6 dB across a splice, no fade_in/fade_out and overlap
  < 100 ms; clip `gain` counts), `duration` (moved out of the engine: warn > 2 s, error only if
  also > 10 % of target). All carry `splice`/`node` ids. Demo: iteration 1 gets `ending` (it stops mid-inst with no fade: real).
- 2026-11-13 — A7 + A8 reviewed (lead session): 174 tests pass. Fresh demo ticket rendered
  end to end; the browser page shows no `not_rendered` left. The demo 02 wash: the return
  tail rings ~4.7 s past the ending splice, peak held at -1.0 dBFS by the limiter. Follow-up
  for Q1: `peak_clip` is noisy on mastered sources → `qc_limiting` (gain reduction > 3 dB).
- 2026-11-13 — A8 done. Devices `utility`, `eq`, `auto_filter`, `reverb`, `delay`, `limiter` on
  clips (tails ring past the clip), tracks, returns and master; device-parameter automation
  (per sample for gain/width/dry_wet, per 512-sample block for filter cutoffs/resonance/
  feedback); `recut.legacy` adapter (old `Clip`/`XFade`/effects -> `Plan`); old effect classes
  emit `DeprecationWarning`. Skill docs (`SKILL.md`, `assets/effects-cheatsheet.md`,
  `effects-routing.md`, `exit-design.md`, new `ending-transplant.md`) and `README.md` use the plan
  vocabulary; the three ending-transplant snippets are rendered by a test. 174 tests pass.
- 2026-11-13 — A7 done. Clip `sends` feed one buffer per return; the return's chain runs once
  over the whole timeline (+10 s pad), the tail is cut where it falls below -60 dBFS
  (`returns_tail_end`), track `volume`/constant-power `pan`, master chain, `peak_dbfs` (output
  level, after the master) and `limiter_applied`. Gain and send automation render per sample.
  `not_rendered` warnings are gone for sends/returns/automation; clip/track devices other
  than reverb/limiter still warn until A8. 144 tests pass.
- 2026-11-13 — D1 + thin slice done. Contracts in `src/recut/contracts/`; engine
  `src/recut/engine.py`; ticket store `src/recut/tickets.py`; review server
  `src/recut/server/` (`recut serve`); CLI `recut ticket ...`. 136 tests pass. Tested in
  headless Chromium: live re-render on a plan.json save keeps the playhead, a broken plan
  shows the error, a review saves and sets `needs_rework`.
- 2026-11-13 — Effects API switched to an Ableton-style model before D1: tracks, clip
  gain/fade handles, devices, sends → return tracks, automation (ramps + points), musical
  units, dB. Replaces `ring_out`/`scope`. A7 rewritten, A8 added. Unit parser moved into D1.
- 2026-11-13 — Added A7 (ending transplant: overlaps, ring-out, scoped fx, limiter) and the
  hosting decision (named tunnel on the operator's domain + Cloudflare Access; share-page
  audio routes). The plan format was extended before D1, so nothing frozen was broken.
- 2026-11-12 — Plan, workstream briefs and this log created. Waiting on: the operator's
  past-session export (prompt in chat) and contracts day (D1).
