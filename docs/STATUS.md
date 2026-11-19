# Build Status / Handoff Log

**Current state (2026-11-14):** week-1 prototype is built and ready for real tickets (none run yet; only the demo ticket and the imported Christmas baseline) (engine, QC + linter, ticket store, review GUI + client share page, data-repo sync, report, intake check); open: B8 (verify Docker on a host), M1 (Demucs stems) and the rest of M3, A6 `RECUT_SESSION` for direct `compose()`, I1 ongoing with real tickets.

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
| A3 LUFS match | done | `engine.match_loudness` (multi-source plans only); `render.json` `sources.<id>.lufs_in/lufs_target`. Tests: `tests/engine/test_loudness.py` |
| A4 render.json | done | `engine.render_plan` → `RenderInfo` |
| A5 cross-song validator rules | done | in `validator/linter.py` (not rules.py): `downbeat` (error, all splices), `bpm_gap`, `key_compat`, `loudness_jump` (warn, cross-source); `validator/camelot.py`. Tests: `tests/validator/test_cross_song.py` |
| A6 session logging | partial | the server/CLI log renders + reviews to `events.jsonl`; `RECUT_SESSION` for direct `compose()` calls is still todo |
| A7 timeline engine: tracks, joins, returns/sends, master | done | `engine.py`, `devices.py` (reverb + limiter), `automation.py` (gain/send ramps + points). Tests: `tests/engine/test_timeline.py` |
| A8 devices, automation, old-format adapter, skill docs | done | `devices.py`, `automation.py`, `legacy.py`; skill docs + README rewritten. Tests: `tests/engine/test_devices.py`, `test_legacy.py`, `test_ending_transplant_doc.py` |
| B1 ticket store | done | `src/recut/tickets.py` |
| B2 FastAPI app | done (no share routes) | `src/recut/server/app.py`, `recut serve` |
| B3 SSE live reload | done | polling, renders stale iterations |
| B4 waveform peaks | done | on request, cached in memory |
| B5 share links | done | `/s/{token}` page + audio, decision API, `recut ticket share` |
| B6 CLI + transcript hook | done (hook untested inside Claude Code) | CLI; `scripts/hooks/copy_transcript.sh` + AGENTS.md settings snippet. Tests: `tests/tickets/test_process.py` (script run with a fake transcript) |
| B7 `recut report` | done | `src/recut/report.py`, CLI `recut report [--since YYYY-MM-DD] [--json] [--root]`. Read-only. Tests: `tests/report/test_report.py` (12) |
| M0 map fixes from the baseline session | done | first section starts at 0.0 (lead-in kept); `bpm` from the beat grid (+ optional `bpm_raw`, load-time guard); `recut map --force [stem...]`; no NaN loudness / zero-length segments. Tests: `tests/map/test_m0.py` (15) |
| L1 ticket timeline + cost | done | `tickets.ticket_timeline(id, root)` merges real `<ticket>/events.jsonl` with entries derived (`"derived": true`) from old timestamps; `src/recut/usage.py` (`parse_transcript`, `write_usage`, `load_usage`, `refresh_stale`, price dict `PRICES_PER_MTOK`) writes `sessions/<n>/usage.json`; `recut sync` refreshes stale usage; `recut ticket show/usage <id>`; `GET /api/tickets/{id}` has `timeline` + per-session `usage`. L2 can call `ticket_timeline` and `usage.load_usage`. The Stop hook does not compute usage itself (next `recut sync` does). Tests: `tests/tickets/test_timeline_usage.py` |
| C0 manual client feedback logging | done | `recut ticket client <id> --approved/--changes [--rating --note]` → `client_feedback.jsonl`; `recut report` section 6 (approval rate, rounds, rating, agreement); ticket page header shows the latest reaction. Tests: `tests/tickets/test_client_feedback.py`, `tests/cli/test_client_cli.py`, `tests/report/test_client_report.py`, `tests/server/test_server.py` |
| B5+ client loop | done | Sonnet: share link → client page with Approve / Request changes, 1–5 rating + comment, consent line |
| L2 report v2 + presentation | done | `src/recut/report_v2.py` (headline, turnaround, cost, baseline vs system, weekly; `overview` in `--json`), `report_html.py` (`recut report --html [--out]`, `GET /report`). Demos excluded everywhere. Tests: `tests/report/test_report_v2.py` |
| L3 baseline import | done | `recut ticket import-legacy <export> [--root DIR] [--force]` → `src/recut/legacy_import.py`; ticket `YYYYMMDD-legacy-<slug>-<hash4>`, session agent `legacy-pre-refactor` = baseline marker; no plan.json (export has no maps). Tests: `tests/tickets/test_import_legacy.py` |
| B8 Docker image | blocked: needs docker to verify | Dockerfile, compose.yaml, .dockerignore, README section written; `docker compose config` ok; build/tests/curl not run. The lead session started dockerd: the base image pulls, but `apt-get` can't reach Debian mirrors from inside containers in this sandbox (network policy, not the Dockerfile). **Verify on the operator's Mac** |
| Q0 intake check (warn operator about low-quality files) | done | `src/recut/intake.py`, `recut check-audio`, `ticket new --override`, `/new` "Upload anyway". Tests `tests/intake/` |
| A9 musical linter rules | done | `src/recut/validator/linter.py` (`lint_plan`, called from `engine.render_plan`); tests `tests/validator/test_linter.py` |
| Q1 audio QC after render | done | `src/recut/qc.py` (+ `qc_essentia.py`, switch `RECUT_QC_ESSENTIA`); engine calls `run_qc`; tests `tests/engine/test_qc.py` |
| Q2 QC follow-ups | done | (a) Essentia QC runs off the critical path: `render_iteration(qc="full"\|"fast"\|"background")`, the server uses `background` (fast render ~0.5 s on the 46 s demo vs ~1.4-2 s with Essentia), `render.json.qc.essentia` = pending/done/skipped, stale results discarded by `qc.render_id`; `recut ticket render --fast`. Tests `tests/tickets/test_qc_background.py`. (b) master limiter is true-peak aware (Q-quality.md Q2b). |
| M1 stems + instrument activity (Demucs on Modal) | done, needs operator check: `modal deploy` + one real track, curves in GUI | Stem audio is **not kept by default** (2026-11-18): Modal returns only the activity curves; `--keep-stems` / `RECUT_KEEP_STEMS=1` returns and saves the FLACs (~150 MB/track). `run_stems` in `src/analysis/pipeline.py` (htdemucs, T4, 600 s, own image from `_base_cuda`; returns 4 FLACs + curves; `analyze_all` spawns it, a failure only logs a warning). Curve maths in `src/recut/map/activity.py` (pure; the Modal copy is kept equal by a test). `analyze_raw` saves stems to `<ticket>/stems/<source_id>/<stem>.flac` (`.appdata/stems/<source>/` outside tickets; `*.flac` is git-ignored in both repos) and puts only curves in the map (`instrument_activity`, `analysis_sources.instrument_activity = demucs-htdemucs`, segment `drum_activity`/`vocal_activity`). Existing maps: `recut map --enrich` / `recut ticket enrich <id>` add activity too (saved stems reused, else Modal for stems only; `--no-activity` skips it). Tests: `tests/map/test_activity.py` (mocked Modal, no GPU) |
| M2 pace + key ranges + short-term loudness | done | `src/recut/map/musicdata.py` (computed in `make_map`; ~4 s for 3 min), Essentia key only via `src/recut/key_essentia.py` (respects `qc_essentia.available()`; else librosa chroma + Krumhansl, source named in `analysis_sources.key_ranges`). Existing maps: `recut map --enrich [stem...]`, `recut ticket enrich <id> [--force]`. Tests: `tests/map/test_musicdata.py` |
| M3 map schema fields + linter rules + GUI lanes | partial | done: optional `pace`, `loudness_short_term`, `key_ranges`, `analysis_sources`, `instrument_activity` (filled by M1), segment `pace`/`drum_activity`/`vocal_activity`; old maps load; GUI pace/loudness lines (toggle "pace / loudness") and drum/bass/vocal lanes (toggle "drums / bass / vocal"), both off by default; linter `ending_drums` and `mid_vocal` (warn, skipped when the map has no activity; `tests/validator/test_linter_activity.py`); `exit-design.md` (pace + activity). Left: nothing to build; verification on a real track (M1 operator check), then tune the thresholds (0.6 drums, 1 beat from vocal-range edges) on real tickets. **A5 (`key_compat`) should call `recut.map.helpers.key_at(map, t)`** (key range at the splice time, falls back to the global key); `pace_at(map, t)` is the energy helper |
| M5 Modal images → Python 3.11 | todo (needs operator) | Modal warns (2026-11-04) that 1.7+ won't deploy Python 3.10 images; `modal<1.7` pinned meanwhile. Change both `python_version="3.10"` in `src/analysis/pipeline.py` to 3.11 (all pinned deps have cp311 builds), `modal deploy`, analyse one known track and compare the map with the previous one (bpm, beats, sections, chords, key), then lift the pin. |
| M4 Apple Music Understanding (Swift CLI) | later | needs an Apple-silicon Mac on macOS 27+ |
| M7 better stem separation for mashups | later (when mashups start) | M1 uses htdemucs: good enough for activity curves, not best for stems you mix with. Before week-2 mashups, add a higher-quality separator as a second Modal function (candidates 2026-11: BS-RoFormer / Mel-RoFormer community checkpoints, SAM-Audio-based models such as MuS3D; check each checkpoint's licence, many are unclear). Keep htdemucs for the curves; compare on 3 known tracks by ear (bleed, artefacts on vocals/drums). |
| C1 scaffold | dropped (decision: no React; app.html covers C2–C7) | |
| C2 ticket list/page | dropped (decision: no React; app.html covers C2–C7) | |
| C3 composition view | dropped (decision: no React; app.html covers C2–C7) | |
| C4 source map | dropped (decision: no React; app.html covers C2–C7) | |
| C5 A/B + live reload | dropped (decision: no React; app.html covers C2–C7) | |
| C6 review panel | dropped (decision: no React; app.html covers C2–C7) | |
| C7 client pages | dropped (decision: no React; app.html covers C2–C7) | |
| I1 integration + real tickets | ongoing (operator: real tickets) | the operator works real client tickets; findings go through `docs/IMPROVEMENT_LOOP.md` |
| R1 convolution reverb (pedalboard Convolution + freely licensed IRs, reverb `type`) | candidate — wait for real tickets | operator on s2·it3 (low-cut return, -26 dB base send rising to -13 dB): "okay for now, needs real cases". Build only when a real ticket shows the algorithmic reverb is the limit |

## Blockers
- **Clip positions in bars use the nominal BPM, not the map's beat grid; there is no way to place a clip at a time** (improvement pass 2, phase 2; ticket 20261118-idzo). `bars_to_seconds` (`src/recut/map/parser.py:75`) is `bars × beats_per_bar × 60 / bpm`, and the engine uses it for `offset_bars`/`bars` (`src/recut/engine.py:149-161`). On a track whose tempo drifts, whole bars miss the real downbeats, and to cut at a heard moment the agent hand-computed fractional bars (11.5213 …), then failed the render: `clip c2: chorus#2 has only 13.44 bars left after the offset; asked for 14.4366 bars` (3 renders, 15:52). Two parts:
  1. **Fixed 2026-11-19**: clip bars/beats count the map's downbeats/beats (`map.parser.advance`) in the engine, compose() and the validator. idzo `chorus#8` now has 14 bars, not 13.44. Automation times and xfade beats stay on the nominal tempo (`parse_time` is in the frozen contracts).
  2. Needs a contract change (§3 is frozen, so the operator decides): a time-based clip field, e.g. `offset_s`/`length_s`, or `at` snapped to the nearest beat. Without it, an edit at a heard moment that isn't on a bar still needs fractional bars.
- (none open from ticket 20261118-jn7o: `-inf` gain lint crash, pause clip, stems as sources and multi-track are fixed, see Decisions 2026-11-18.)
- (otherwise none open) Note: `examples/summer-party/summer-party-map.json` predates M0 (NaN loudness on a zero-length `silence`, an `inst` ending before the audio). It is not regenerated (no raw data); it still loads (NaN is read as the -200 dB floor).

## Decisions
- 2026-11-19 — Clip `bars`/`offset_bars`/`beats`/`offset_beats` count the map's real downbeats/beats; fractions interpolate within a bar, and the nominal tempo extends the grid past its ends. Nominal BPM made a section's real bars "not fit" on drifting tempo (idzo: 13.44 of 14). Skill `map-interpretation.md` updated; its exact-end false-positive advice is obsolete.
- 2026-11-18 — `recut sync` prints what each status means (`queued`: another sync pushes it, nothing to do; `push-failed`: committed locally, re-run where git reaches the remote). AGENTS.md: commands for the operator go in their own code block with no trailing punctuation. Agents had re-run queued syncs with the sandbox off; the operator pasted `recut sync.` twice.
- 2026-11-18 — usage.json `duration_s` is active time (waiting over 5 min for the operator's next prompt counts as 5 min; tool runs count in full; `wall_s` keeps first-to-last), and `model` is `mixed` when a session switched models. Wall-clock had counted hours of operator absence (ypag 377 min, now 109 active; fzsv 300, now 31). Older usage.json files are recomputed at the next sync. Not fixed: dev chat after the ticket in the same session still counts.
- 2026-11-18 — `import recut` sets `NUMBA_CACHE_DIR` to `~/.cache/numba-recut` unless set: in a sandbox every Python call failed with numba's "no locator available". AGENTS.md no longer hard-codes one operator's Python path (it's the `python` next to `recut`).
- 2026-11-18 — ffmpeg/ffprobe are looked up on PATH, then next to the running Python (`intake.tool`), for MP3 export and intake. Two tickets hit "ffmpeg not found" while the conda env had it (~55 min lost installing another copy).
- 2026-11-18 — `recut serve` restarts when recut's code changes (default; `--no-reload` opts out). A server left running across the `gap` merge failed 26 GUI renders in 4 tickets while the CLI rendered fine.
- 2026-11-18 — From ticket 20261118-jn7o (voice FX between two songs; 7 iterations, mostly workarounds), general fixes: plan v2 gets a `gap` node (pause) and **multi-track** (tracks are layers from 0 s, a leading gap places one; buses summed, all send to returns; segments carry `track`); a separated **stem is a source** with its song's map, and a song's sources share one loudness-matching gain so a stem keeps its balance; `layer_level` info issue (layer entry loudness vs the main track); `recut ticket audition <id> <source>` writes short phrase files for the operator to pick an FX by ear in one round; export file named after the client; `-inf` clip gain lint crash fixed; missing `run_stems` prints the fix. Cutting skill: `references/sound-fx.md`, sources are level-matched (no make-up gain). Render time was not a problem (4.5 s; "Rendered …: 138.6s" is the cut's length). Stems are now kept by default (operator decision: any stem can be an FX or a layer; `RECUT_KEEP_STEMS=0` / `--no-keep-stems` turns it off). Code review (high) fixes: planned gaps are not `qc_gap` defects; a stem without its mix in the plan still gets its song's gain; sequence/ending checks stay on the main track when layers exist; export never overwrites another ticket's file; auditions read every intake format; GUI source view follows the main track.
- 2026-11-15 — For now cuts go to clients via Google Drive (`recut ticket export`, logged with
  `recut ticket client`). The share page stays built but unused until the operator wants a public
  URL (Cloudflare). Fixed: `recut ticket share` CLI handler had been lost in a merge.
- 2026-11-14 — A5: rules live in `validator/linter.py` (next to A9, called from the engine) and get the level-matched source audio. `downbeat` checks the join of each side: incoming = clip `src_start`; outgoing = `src_end` minus the xfade overlap (an overlap under 100 ms is a click cover and doesn't shift it), against the map's `bars` (downbeats), 30 ms. `loudness_jump` is the source/map-level check (3 s short-term window of the outgoing source before the cut vs the incoming source after it, clip gain included, > 3 dB); it is kept separate from `qc_gain_jump` (400 ms on the rendered audio, catches fades/devices), so they differ in window and data. `bpm_gap` uses 3 % and accepts 2:1 within 3 %.
- 2026-11-14 — A3: target LUFS = min(loudest source, -9) rather than a fixed -14 (PLAN §2 said match, the A3 task said -14): never makes loud masters louder, and quiet sources aren't dragged below the loudest. Gain is applied to a copy; peaks above 0 dBFS are left to the master limiter.
- 2026-11-14 — The operator creates every ticket; clients only listen and answer on the share link.
  `/new` and `POST /api/tickets` are operator-only (behind Cloudflare Access); public paths are
  only `/s/*` and `/api/share/*`. Q0 warns the operator instead of the client.
- 2026-11-14 — Ticket data is saved to the private repo `mewdev/recut-data` (sibling checkout,
  auto commit + push after every ticket action, audio excluded); see PLAN §3.7. The Christmas
  pre-refactor session is the first baseline (`recut-data/baseline/pre-refactor/`).
- 2026-11-13 — Essentia's Intel-Mac wheel aborts Python on import (native "Failed loading
  SDL2 library" dialog; no try/except can catch it). `qc_essentia` is now off by default on
  darwin/x86_64, probes the import in a child process before importing in-process, and the
  `qc` extra skips Essentia on Intel Macs. Intel-Mac install also needs
  `--only-binary=llvmlite,numba,cbor2` (README).
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
- 2026-11-18 — Improvement pass 2, fix 3 (endings). Evidence: 20261118-idzo, 4 rejected endings (it1-it4) built from the song's loud finale ("something more natural ... the ending is using some loud strings ... ideally harmonically cohesive"); the operator had to propose the single chord hit; then it5 "string subdivision playing after the last tone", it6 drum-stem kick ~150 ms late (aligned on a roll's onset), it7 stem switch dropped the drums ("some kinda cut"); 20261118-fzsv it2 reverb tail too weak at a -12 dB send peak. `ending_drums` fired on every hit ending (it5-it9, the shipped one too). Skill (`skills/cutting/references/exit-design.md`): "Match the ending to the request first" (character words, measure the ending against the bars before the cut, harmonic continuity) and exit type 4 "Final chord hit" (hit alone, click-cover fade, reverb bloom send levels, drum hit aligned on its impact, keep stems across a stem switch, layer a second attack instead of gain); music-theory exit-design points to it; navigation row. Linter: `ending_drums` ignores a `fade_out` under 100 ms (a click cover, same convention as `SMOOTHING_XFADE_MS`). Tried and dropped: a `layer_timing` lint (layer peak vs the main track's beat): on the real drum stem the loudest point is the cymbal ring, not the impact (the accepted kick read +153 ms), so it would be noise; the rule stays in the skill. Skills changed on mostly one session's evidence, with the operator's explicit OK (pass 2). Tests: `tests/validator/test_linter_activity.py::test_ending_drums_ignores_a_click_cover_on_a_final_hit` (fails on the old linter), `tests/engine/test_exit_design_doc.py` (the recipe renders with a ringing tail, no `ending`/`ending_drums`/`qc_limiting`). No ticket fixture: idzo's plan needs its stems as sources.
- 2026-11-18 — Improvement pass 2, fix 2 (song changes and joins that are not edits). Evidence: 5hiy and ypag (song A whole, then B) both failed it2 the same way, operator: "second song needs to start earlier ... additional silence which makes the gap too long"; the dead air sat in a `gap` node, which `qc_gap` ignores as deliberate, so nothing flagged it. The song change drew `downbeat`, `key_compat`, `bpm_gap`, `loudness_jump`, `phrase_align`, `qc_gain_jump`, and the 5hiy agent added a fake 10 ms gap to silence them; contiguous joins (same source, the song plays on) drew `mid_vocal`, `energy_drop`, `qc_gain_jump`, `qc_tilt_jump` (fwmf agent: "false positives"). Linter: a song change = consecutive main-track clips where the outgoing reaches its song's last music (within a bar) and the incoming starts its first; new `song_change_gap` (info with the number, warn > 2 s) = outgoing tail below -50 dBFS (50 ms RMS, clip gain included) + time between the clips (gap nodes) + incoming lead-in; splice rules skip song changes and contiguous joins (same source, sample-contiguous, same gain, no fades); QC `qc_gain_jump`/`qc_tilt_jump` skip them too. On the real audio: 5hiy it2 2.8 s / ypag it2 2.9 s warn, shipped it3 1.4 s / 0.5 s clean. Issue noise on the other tickets' final plans dropped (fwmf it1 6 to 1, fzsv it3 6 to 2, idzo it7 10 to 3) while the complained-about splices still flag (jn7o it5 s2 gain jump, idzo it7 s10 brightness jump). Threshold 2 s, not the 1 s first proposed: shipped 5hiy measured 1.4 s. Skill: new `skills/cutting/references/song-sequence.md` (no dead air, count the lead-in, pause in seconds = audible silence; moved out of `sound-fx.md`, which only voice-FX requests reach), navigation row, SKILL.md. Tests: `tests/validator/test_song_change.py` (fixtures `tests/fixtures/regressions/20261118-5hiy/`, `-ypag/`: real maps + it2/it3 plans, synthetic audio with the measured tail; 6 of 7 fail on the old code).
- 2026-11-18 — Improvement pass 2, fix 1 (transparent master limiter). Evidence: the default master limiter was pedalboard's JUCE Limiter, a 4:1 compressor above -10 dBFS with make-up gain: a -20 dBFS sine came out +3.75 dB, a -3 dBFS one at -4.3 dBFS. Every default-master render changed audio nobody edited: fzsv it1 +3.6 dB in quiet passages (agent then spent 5 renders on a utility trim), ypag shipped +1.45 LU over its source (`qc_loudness` on all 3 iterations), 5hiy it1 +1.46 LU, idzo agent removed the limiter and then clipped every layer (7 renders at it6). Also `exact_true_peak` read each chunk's zero-padded edges, which rang up to ~1.2 dB high (fzsv source: +0.99 read, -0.26 dBTP real), so limited renders got a needless static trim. Now `devices.limit` computes the gain each 4x-oversampled sample needs, min-filters then averages it over 2 x 5 ms (never above the needed gain, gain exactly 1 away from overs), keeps the static true-peak trim as a safety net; `_true_peak_env` reads only each chunk's own span and skips chunks 3 dB (limiter) / 6 dB (trim) under the ceiling. `_limiter` always goes through it (no whole-track trim for an inter-sample over). Cost: ~3.6 s vs ~2.6 s on a 3:44 loud master. Tests: `tests/engine/test_limiter_transparent.py` (regression fixture `tests/fixtures/regressions/20261118-fzsv/`, synthetic loud master; 3 of 4 fail on the old code). Report baseline for this pass (since 2026-11-13, n=6, all agent-entered reviews): ship 100 %, first-attempt ship 17 %, median 3 iterations to ship; pass 1 recorded no rate, so this is the baseline.
- 2026-11-18 — Transcript hook no longer lets two Claude sessions on the same ticket session overwrite each other (ticket 5hiy: a second session replaced the first one's transcript; repaired by hand). `scripts/hooks/merge_transcript.py` (stdlib) keeps `transcript.jsonl` as the concatenation of every Claude session's transcript and replaces only the block(s) of the sessions in the incoming copy; lines without a `sessionId` (file-history snapshots) get their session's id written in, so block boundaries stay unambiguous. Without python3 the hook only creates a missing file. Tests: `tests/tickets/test_process.py::test_hook_keeps_every_claude_session_of_one_ticket_session` (fails on the old hook); dry run on the real 5hiy transcript gives two blocks identical to their originals.
- 2026-11-18 — Transcript hook routes by Claude session, not a shared pointer. Bug: `recut ticket work` wrote one `<tickets>/.current_session`, so with several agents open every Stop hook copied its transcript into whichever ticket ran `work` last (ticket fzsv got the transcripts of the idzo, 5hiy and ypag sessions, overwriting its own; repaired by hand from `~/.claude/projects`). Now `tickets.mark_agent_session` writes `<tickets>/.agent_sessions/$CLAUDE_CODE_SESSION_ID` and `scripts/hooks/copy_transcript.sh` reads the pointer named by the `session_id` on its stdin; `.current_session` is no longer read or written, and a session without a pointer copies nothing. `sync` now adds new ignore patterns to an existing data-repo `.gitignore` (pointers stay machine-local). Tests: `tests/tickets/test_process.py::test_hook_routes_parallel_agents_to_their_own_tickets` (fails on the old hook), `test_mark_agent_session`, `tests/sync/test_sync.py::test_sync_adds_new_ignore_patterns_to_an_older_gitignore`.
- 2026-11-18 — Operator reviews given in an agent session are now recorded by the agent: `recut ticket review <id> --verdict … [--ok all|ids] [--bad sN:tag+tag] [--tags …] [--note …]` saves the same `review.json` files as the GUI (`tickets.save_review`), checks splice ids against `render.json` and tags against `TAGS`, appends a provenance line to the note, and syncs. The verdict always comes from the operator (AGENTS.md step 7). The Stop hook (`copy_transcript.sh`) blocks the stop once per rendered, unreviewed iteration (marker in `$TMPDIR`, honours `stop_hook_active`) so the agent asks. Tests: `tests/cli/test_review_cli.py`, `tests/tickets/test_process.py`.
- 2026-11-14 — Q2a done (Sonnet build agent): Essentia QC runs after `render.json` is written. `run_qc(deep=False)` does the basic detectors and leaves `info._deep()`; `tickets.render_iteration(qc=...)` merges the Essentia issues (`qc_clipping`, `qc_click`, `qc_gap`, `qc_backend`) and numbers atomically in a thread; the app.html Problems panel shows "deep checks running…" while pending. Fast path: ~0.5 s on the demo (full: 1.4-2.0 s).
- 2026-11-14 — Q0 done (Sonnet build agent): `intake.check_audio(path) -> IntakeResult{ok, problems[{code,message,blocking}], info}` (ffprobe metadata, only the middle 30 s decoded; real bandwidth via `qc.bandwidth_hz`; clipping via the numpy `qc.clip_runs`, because the Essentia detectors are too slow for a sub-second check). `recut check-audio`; `recut ticket new` refuses blocking problems without `--override`; `POST /api/tickets` returns 422 `{detail:{error:"intake",problems}}` unless `override=true`, `/new` shows them with an "Upload anyway" checkbox (not checked in a browser). Problems + override are stored in `<ticket>/intake.json` and an `intake` timeline event (the `Request` contract is untouched). Note: bandwidth reads ~16 kHz for a 15 kHz low-pass (the -40 dB point of a real filter's skirt). 5-min file: ~0.2 s WAV (see report).
- 2026-11-14 — A5 done (Sonnet build agent): cross-song linter rules, see the Decisions entry. Demo plan 01 (a→b, 2-beat overlap) fires one real `downbeat` error: the incoming downbeat lands on beat 3 of the outgoing bar. bpm/key/loudness don't fire (same song, a/b level-matched by A3). The doc recipe `ending-transplant.md` variant 3 used a 2-beat xfade with the same flaw; changed to `1 bar`.
- 2026-11-14 — A3 done (Sonnet build agent): multi-source plans are gained to one integrated loudness at load (target = loudest source's LUFS, capped at -9, so quiet sources come up and loud masters are never made louder); single-source plans are untouched (test: identical samples). Measured with `qc.integrated_lufs` (pyloudnorm-equivalent, within 0.01 LU), cached per file+mtime. Demo medley: a and b (-6 dB apart) now render level-matched.
- 2026-11-14 — L2 done (Sonnet build agent): `recut report` leads with a headline block, then turnaround, cost (API-equivalent), baseline vs ticket system and ISO-week trend (`overview` in `--json`); n shown everywhere, n < 5 = "too few to judge". Baseline tickets (agent `legacy-pre-refactor`) have date-only timestamps, so they are left out of turnaround and cost. `recut report --html` and operator-only `GET /report` serve a self-contained page (inline SVG, no external requests; checked in Chromium at 1200 and 390 px, light + dark). Existing report sections now skip demo tickets too (`test_demo_fixture` updated).
- 2026-11-14 — L3 done (Haiku build agent): `recut ticket import-legacy`. Maps a pre-refactor export to one ticket (session 1, agent `legacy-pre-refactor` = baseline marker, model null); reviews keep contract fields only (`human_fix` appended to the note as "human fix: …"); `client_approved` becomes a manual `ClientFeedback` line dated at the export date. plan.json is not written: the export has no maps, and `recut.legacy` needs the segment map. Re-import is refused unless `--force`. Verified on the real export into a tmp root: `recut report` counts 1 ticket, 1 reviewed session, overall fixable 1, client approval 1/1. **Operator: run `recut ticket import-legacy ../recut-data/baseline/pre-refactor/20261015-like-its-christmas-cut` on the Mac** (writes into recut-data/tickets and auto-syncs). 297 tests pass.
- 2026-11-14 — M0 done (Sonnet build agent): general map fixes from the pre-refactor baseline session. (1) First segment starts at 0.0 (`make_map.build_segment(is_first)`), so a pickup/lead-in is never dropped; `bars`/`downbeats` count real downbeats only; engine `offset_bars/beats` count from the first downbeat (`engine._clip_bounds`); documented on `EnrichedSegment`. Zero-length segments (two raw boundaries snapping to one downbeat) are dropped and indices renumbered. (2) `MusicMap.bpm` = 60 / median inter-beat interval (`recut/map/tempo.py`); the estimator value goes to optional `bpm_raw` when it differs > 5 % (warning). `parse_recut_map*` corrects old maps from their own grid with a warning, so existing tickets are fixed without re-analysis. `src/analysis/pipeline.py` `run_beats` returns grid bpm + `bpm_estimate` (verbatim copy of the helper; a test keeps them equal). **Needs a Modal redeploy (`modal deploy src/analysis/pipeline.py`) to take effect for new analyses.** (3) `recut map --force [stem ...]` rebuilds existing maps that have raw analysis. (4) Loudness of empty audio is `LOUDNESS_FLOOR_DB` (-200), NaN read from old maps becomes the floor; map JSON is valid (`allow_nan=False`). Existing maps keep the old first-segment start until rebuilt with `recut map --force`. 267 tests pass.
- 2026-11-14 — C0 done (Haiku build agent): manual client feedback. `tickets.add_client_feedback` (defaults to the latest
  shipped iteration, else the latest; appends to `client_feedback.jsonl`, logs `client_feedback` to events.jsonl, sets
  `client_approved`/`client_changes`), `load_client_feedback`, CLI `recut ticket client` (auto-synced), report section 6,
  `client_feedback` in `GET /api/tickets/{id}`. Tests added in the four files above.
- 2026-11-14 — Data repo set up: `mewdev/recut-data` (README, CLAUDE.md, .gitignore, first
  baseline). `recut.sync` + `recut sync`; auto-sync from CLI, server and hook; tests isolated
  from the real data repo (conftest sets RECUT_TICKETS_DIR + RECUT_AUTOSYNC=0). 251 tests pass.
- 2026-11-13 — B7 done (Haiku build agent): `recut report` (`src/recut/report.py`, read-only). Five sections: success rate (overall / per model / single vs multi-song; reviewed sessions only, result = highest reviewed iteration's verdict), failure tags (grouped per B-backend, `fx_wrong` under engine), validator misses (bad splices with no render issue on that splice), worst 5 sessions, and check accuracy (per issue rule: flagged splices marked bad vs ok). `--json` prints the same data. Per-iteration reviews are used. Tests: `tests/report/test_report.py` (12, hand-built fixture: ship/fixable/reject, single/multi-song, two models, one unreviewed session, a validator miss, a check-accuracy case). Suite: 245 pass.
- 2026-11-13 — Improvement pass 1, task 3 (enforce the agent process; evidence: the s2 agent wrote no `intent.json`, kept no
  transcript, and its plan `notes` were the only record). `recut ticket render` prints `WARNING (process)` lines for a missing or
  invalid `intent.json` and for `plan.notes` empty / identical to the previous iteration's (CLI only: no render.json change, no
  contract change). `recut ticket work` prints a ready-to-fill `intent.json` snippet (valid `Intent` keys) instead of creating a
  file, the `export RECUT_SESSION` line, and a note about the transcript hook. B6 hook: `scripts/hooks/copy_transcript.sh`
  (stdin JSON `transcript_path`, destination `$RECUT_SESSION` or `.appdata/tickets/.current_session`, always exit 0); enable
  snippet in AGENTS.md. NOT verified: a real Claude Code Stop hook run (tested with a fake transcript only; the stdin JSON shape
  is from the hooks docs, not observed).
- 2026-11-13 — Improvement pass 1, task 2 (QC relative to the source; evidence: every render of the loud demo gave
  `qc_loudness` -8.9 LUFS and `qc_true_peak` +0.06 dBTP). `qc_loudness` now compares the render with the source ranges it
  uses (warn > 1 LU louder than the loudest, > 3 LU quieter than the weighted mean; absolute window only when there is no source);
  numbers `lufs`, `source_lufs`, `lufs_vs_source` in `render.json.qc`. `devices.limit` trims the 4x true peak to the ceiling with
  one static gain (about 1 dB on the demo; `limit()` now returns `(audio, trim_db)`; QC discounts the trim from `qc_limiting`, so
  the sample peak of a limited render is now ~1 dB under the ceiling). Demo variants: no qc_loudness / qc_true_peak left. Tests:
  `test_qc.py` (unchanged loud source: no warning; +3 dB: warning; limited render: true peak <= ceiling + 0.1 dB), `test_timeline.py`.
- 2026-11-13 — Improvement pass 1, task 1 (reverb recipe rules; evidence ticket 20261113-mbyv, s1·it2 "reverb squash" 3.4 dB
  limiting, s2·it2 "much better, still turned on", s2·it3 "okay for now"). `ending-transplant.md`, `effects-routing.md`,
  `effects-cheatsheet.md`: return `eq` low_cut 200-300 Hz before the reverb, decay 1.5-2.5 s, send peak -9 to -13 dB (never 0 dB
  on a 100 % wet return), no ramp from `-inf` (base -24 to -30 dB, ramp >= 2 beats). Variant snippets updated. Tests in
  `test_ending_transplant_doc.py`: every variant renders on the loud demo source with no `qc_limiting` and gain reduction <= 3 dB
  (2.3-2.8 dB; the source alone limits 2.3-2.5 dB), the doc follows the recipe, and the old 3.5 s / -inf to 0 dB wash limits
  harder (3.44 dB, matches the ticket). `examples/summer-party/plans/02-ending-transplant.json` is the old recipe, left as is.
- 2026-11-13 — First real review (operator, demo ticket): it2 s3 bad, "reverb squashes,
  needs to be more subtle, probably reverb type + automation". `qc_limiting` (3.4 dB) agreed
  with the ear; `qc_tilt_jump` at s3 wasn't mentioned (likely noise). No tag fitted, so
  `fx_wrong` was added. Likely cause: full-range send into the reverb on a loud master (kick
  and bass in the reverb pump the limiter); the DAW fix is a return low-cut of ~300–500 Hz,
  a lower send and a shorter decay. Recipe deliberately not changed yet: session 2 tests
  whether the agent finds it from the review alone. Candidate task: convolution reverb.
- 2026-11-13 — A9 + Q1 merged and reviewed (lead session): 210 tests pass with and without
  Essentia. Demo it2 issues: qc_loudness −8.9 LUFS, qc_limiting 3.4 dB, qc_true_peak +0.1
  dBTP, qc_tilt_jump at s3 (chorus → inst contrast); Essentia's 7 source transients become
  one info issue. Follow-ups logged as Q2.
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
- 2026-11-13 — B8 files written (Haiku build agent, worktree on claude/audio-edit-app-workflow-uu5tee): `Dockerfile`
  (python:3.11-slim, ffmpeg + libsndfile1, `pip install -e ".[dev]"`, no secrets), `compose.yaml` (service `recut`,
  `recut serve --host 0.0.0.0 --port 8000`, mounts `./.appdata` and `~/.modal.toml:ro`, restart unless-stopped),
  `.dockerignore`, README "Run with Docker". Verified: `docker compose config` resolves; `ruff check .` clean; 174 tests pass
  locally. NOT verified: `docker build`, tests in the container, `curl localhost:8000/api/tickets`. Docker CLI is
  installed but the daemon is not running here (no /var/run/docker.sock). Needs a run on a host with Docker before B8 is done.
  Note: `~/.modal.toml` must exist on the host before `docker compose up`, or Docker creates a directory in its place.
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
- 2026-11-14 — B5/B5+: client share page (`/s/{token}`, Cut/Original, approve/changes, stars, consent), share + decision API, operator "Create client link" button, `recut ticket share`.
- 2026-11-13 — Added A7 (ending transplant: overlaps, ring-out, scoped fx, limiter) and the
  hosting decision (named tunnel on the operator's domain + Cloudflare Access; share-page
  audio routes). The plan format was extended before D1, so nothing frozen was broken.
- 2026-11-12 — Plan, workstream briefs and this log created. Waiting on: the operator's
  past-session export (prompt in chat) and contracts day (D1).
- 2026-11-14 — L1: ticket timeline (events.jsonl, derived backfill) and session usage/cost from transcripts; CLI `ticket show|usage`, API fields.
