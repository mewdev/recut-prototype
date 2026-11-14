# Changelog

## [0.2.0] — 2026-11-14 — Ticket workflow: plan v2 engine, review GUI, QC, client loop

Everything since the 0.1.0 MVP (`cbe0e35`). The old `Clip`/`XFade` composition API still works
(deprecated); new work goes through `plan.json`.

**Ticket system + review GUI**
- Tickets are plain folders (`.appdata/tickets/<id>/`: request, inputs, maps, sessions, iterations); `recut ticket new/list/work/iterate/render/show/usage/enrich/demo`; session `intent.json`, `plan.notes` and process warnings
- `recut serve`: FastAPI review page (no build step, `src/recut/server/static/`): composition + source-map view, A/B, waveform peaks, live re-render over SSE, per-splice review tags + verdicts, pace/loudness lines
- Transcript Stop hook and SessionStart reminder scripts (`scripts/hooks/`); per-ticket timeline (`events.jsonl`) and per-session usage/cost from transcripts

**Plan v2 engine (Ableton-style)**
- Contracts in `src/recut/contracts/` (plan, render.json, ticket) with musical units (bars/beats, dB); `engine.render_plan`: multi-source timeline, clip gain and fades, overlaps, tracks (volume/pan), return tracks with sends and ringing tails, master chain, true-peak-aware limiter, gain/send/device automation (ramps + points)
- Devices: `utility`, `eq`, `auto_filter`, `reverb`, `delay`, `limiter` (`devices.py`); multi-source plans are LUFS-matched on load (A3)
- `recut.legacy` converts old `Clip`/`XFade`/effect compositions to plans

**Linter + audio QC**
- Musical linter (`validator/linter.py`): `phrase_align`, `ending`, `energy_drop`, `duration`, cross-song `downbeat`, `bpm_gap`, `key_compat` (key in force at the join), `loudness_jump`
- Audio QC after every render (`qc.py`; Essentia detectors in `qc_essentia.py`, switch `RECUT_QC_ESSENTIA`, numpy/scipy fallback): loudness relative to the sources, limiting, true peak, clipping, clicks, gaps, DC/phase, gain/tilt jumps, bandwidth
- Essentia QC runs off the critical path for the live preview (`render.json.qc.essentia` pending/done/skipped); `recut ticket render --fast` skips it
- Intake check for uploaded audio (`recut check-audio`, `ticket new --override`)

**Data repo + client loop**
- Ticket data auto-syncs to the private `recut-data` repo (`recut sync`); baseline import of pre-refactor sessions (`ticket import-legacy`)
- Client share page (`/s/{token}`: Cut/Original, approve/request changes, rating, consent), `recut ticket share`, manual client feedback (`recut ticket client`) and the operator reminder for shipped cuts without feedback
- `recut report` v2 (headline, turnaround, cost, baseline vs ticket system, weekly trend), `--html` page and `/report`

**Map**
- M0 fixes (first section from 0.0, beat-grid `bpm`, `map --force`, no NaN loudness); M2/M3 pace, short-term loudness and key ranges (`map --enrich`, `ticket enrich`), helpers `pace_at`/`key_at`
- Last segment runs to the end of the audio

**Docs / skills**
- README rewritten for the ticket workflow; `cutting` and `music-theory` skills use the plan vocabulary (reverb return recipe, ending transplant, exit design); Docker image files (unverified, see `docs/STATUS.md` B8)

## [feat] — 2026-08-21 — Project registries, multi-source prep, xfade curve/beats

**Source registry** (`src/recut/project.py`, new `src/recut/paths.py`)
- Scans `.appdata/audio/` for audio files, classifies each stem: `ready / needs_map / needs_analysis / hash_mismatch`
- `hash_mismatch`: audio hash verified against map's `meta.audio_hash` — stale maps detected
- `verify_source_hash()` helper

**Composition registry (#40)**
- Save/load/list named edit plans → `.appdata/compositions/<name>.json`
- `Composition` dataclass: name, sources, nodes, created
- Clip/XFade node JSON serialization round-trip; fx skipped on purpose for now
- `create_composition()`, `save_composition()`, `load_compositions()`

**CLI**
- `map` — now argless batch command: builds enriched maps for all sources with status `needs_map`
- New `status` command — registry state for all sources in `.appdata`
- New `compositions` command — lists saved compositions
- `analyze` copies the audio file into `.appdata/audio/`

**Multi-source prep (arch)**
- `Clip.source: Optional[str]` — key into the sources dict passed to `compose()`; `None` = default single source (backward compatible); enables multi-file compositions
- `ValidationResult.source: Optional[str]` — which source a validation result refers to
- `Rule.domain` / `SequenceRule.domain = "song_reshape"` — rules tagged by domain for future rule sets

**XFade**
- New shared module `primitives/curves.py`: `Curve` type + `make_envelope(vol_start, vol_end, n, curve)` — linear/log/exp/qsin, used by fade and xfade (dedup)
- `xfade(xfade_ms=500, curve="qsin")` — curve param replaces hardcoded sqrt ramps; qsin quarter-sine = equal-power default
- `XFade.beats: Optional[float]` — if set, compositor resolves duration from map BPM (`beats_to_seconds × 1000`) instead of `ms`
- Guards: sample-rate mismatch, channel-layout mismatch, stricter length check (`>=`)
- `Audio.num_channels` property
- Validator checks/rules updated to match

**Tests**
- New `tests/primitives/test_primitives.py`, `tests/cli/test_cli.py`, `tests/project/` (source + composition registry)

---

## [chore] — 2026-08-19 — Pipeline remote cloning, test restructure, README, cleanup

**Analysis pipeline — remote model cloning**
- Removed `add_local_dir` — models no longer bundled or pushed from local disk
- `chords_image`: clones `ptnghia-j/chord-cnn-lstm-model` via `git lfs` at Modal deploy time
- `structure_image`: sparse-checkout of `SongFormer/` from `mewdev/ChordMiniApp` fork; weights downloaded from HuggingFace at image build time (`GIT_LFS_SKIP_SMUDGE=1` to avoid LFS bandwidth limits)
- Pipeline output path updated: `.appdata/maps/raw/<stem>-raw.json`
- License comment block added to `pipeline.py` — MuQ is CC BY-NC 4.0 (non-commercial only)

**Models removed from repo**
- `src/analysis/models/` deleted and untracked — no longer needed, cloned remotely
- `.gitignore` entry for `src/analysis/models/` removed (folder gone permanently)

**Test structure**
- Tests reorganised into subdirectories mirroring `src/recut/`: `tests/map/`, `tests/validator/`, `tests/primitives/`
- Real song fixture (`end_of_beginning-map-v0_1.json`) replaced with synthetic `sample-map.json` — 120 BPM, clean round numbers, no real song data
- Test assertions updated to match synthetic fixture values

**README**
- CLI paths updated to `.appdata/maps/`
- Compositor code example added (fabricated track, real API)
- Validation section added — purpose, code snippet
- Third-party attributions table with repo links and licenses
- Music map format hidden under `<details>` — replaced with one-line description
- Modal deploy note: models clone automatically, no manual setup

**`.appdata/` convention**
- All app-generated files (raw JSON, enriched maps) go to `.appdata/` — git-ignored

---

## [refactor] — 2026-08-19 — Refactor: namespace package + Pydantic schema + plain-function pipeline

Implemented colleague code review feedback (2026-08-18). Full structural overhaul across 5 steps.

**Step 1 — `src/recut/` namespace package**
- All source moved from `src/` into `src/recut/` — prevents shadowing third-party packages
- All imports rewritten from bare (`from audio import`) to namespaced (`from recut.audio import`)
- `Loop` class merged into `Clip(loop=N)` — simpler API, `Node = Clip`
- `SegmentLabel`/`label` renamed to `SegmentName`/`segment_name` throughout (including map JSON)

**Step 2 — Schema: TypedDict → Pydantic BaseModel**
- All output types (`EnrichedSegment`, `MusicMap`, `Sources`, `Meta`, `ModelRef`, `KeySignature`) converted to `BaseModel`
- Input types (`ChordEntry`, `RawSegment`, `RawAnalysis`) kept as `TypedDict` — raw dicts at runtime
- `typing_extensions.TypedDict` required for Pydantic v2 on Python < 3.12
- `make_map.py` updated: constructors replace `dataclasses.asdict()`, `result.model_dump()` for JSON serialization

**Step 3 — Parser: ABC + classes → plain functions**
- `OurMapParser` class + `MapParser` ABC deleted
- `parse_recut_map(path)`, `parse_recut_map_dict(src)` — trivial one-liners (Pydantic handles validation)
- `parse_muf_map`, `parse_muf_map_dict` — stubbed with `NotImplementedError`
- 5 pure MusicMap helpers added: `get_segment`, `bars_to_seconds`, `beats_to_seconds`, `first_segment`, `last_segment`

**Step 4 — Validator: `MapParser` → `MusicMap`**
- `validate(music_map, *nodes)` — no parser dependency
- All checks use free functions from parser; dict access replaced with attribute access

**Step 5 — Compositor: `MapParser + path` → `MusicMap + Audio`**
- `compose(music_map, audio, *nodes)` — no parser, no `audio_path` string, no `skip_validation`
- Downbeat snap: `"audio_start" in segment` → `segment.downbeats` (truthy check on list)
- `pyproject.toml` script entry fixed: `"cli:main"` → `"recut.cli:main"`

---

## [refactor] — 2026-08-12 — src/ layout migration + tooling fixes

Reorganized project into a clean `src/` package layout for better overview.

**Changes:**
- All source moved into `src/`: `compositor.py`, `audio.py`, `nodes.py`, `map_parser.py`, `primitives/`, `map/`, `validator/`, `tests/`
- `ui-map-editor/` moved to `src/map/ui-editor/` — co-located with the map subsystem it serves
- `pyproject.toml`: `pythonpath = ["src"]` — pytest resolves bare imports correctly
- `.vscode/settings.json`: `python.analysis.extraPaths = ["src"]` — Pylance now agrees with pytest on bare imports, stops auto-prefixing `src.`
- `archive/` excluded from both ruff and Pylance
- Test fixtures committed to `src/tests/fixtures/`
- `StubParser` completed with `first_segment()`/`last_segment()` — gap exposed by `check_sequence_boundaries` rule
- Pre-commit checklist updated: ruff + pytest both required

---

## [analysis] — 2026-07-03 — MUF architecture reverse-engineering + map enhancement plan

Fully reverse-engineered Apple's `MusicUnderstanding.framework` (iOS/macOS 27.0) from `.swiftinterface`, `.tbd`, binary strings, CoreML MIL files, and live runtime output.

**Key findings:**
- 4 separate CoreML models: DownbeatTracker (ConvNeXt CNN + JointHMM), KeyModel (repurposed chord detector), InstrumentActivityModel (6-bit quantized CNN), StructuralFeaturesModel (distilled CNN, 204s receptive field)
- Beat tracker = CNN observation model + HMM decoder (same architecture as madmom DBNBeatTrackingProcessor)
- 3-level structure hierarchy: sections → segments → phrases (Apple finds 29 phrases on a 2:39 track)
- Instrument activity = 4-class presence classifier (not stems) — 10× lighter than Demucs
- Pace output = cuts-per-minute recommendation (41-class, 0–80 cuts/min per section)
- `VideoCuesProvider` (direct Recut analog) fully implemented in binary — model simply not bundled

**Map comparison (end_of_beginning.mp3):**
- Our map: 6KB, named labels, chords, LLM-optimized
- Apple MUF: 3.8MB, sample-precise (÷44100), no labels, no chords
- Boundary agreement: ~0.1s on well-tracked sections, up to 3s disagreement on others
- Strategy: MUF precision where aligned, our labels as semantic layer, chords as tiebreaker

**Enhancement plan:** See `todo-and-ideas.md` → "Map schema v3" section.
Reference: `MusicUnderstandingFramework/MusicUnderstanding_framework_architecture.md`, `MusicUnderstandingFramework/comparison.md`, `learning/music_analysis_guide_for_musicians.md`

---



## [map v2] — 2026-06-10 — Downbeat snapping with drift fallback
**Track tested:** end_of_beginning.mp3 (testing/04)

Improved segment boundary accuracy in `map/make_map.py`:

- **`snap_to_downbeat()`** replaces naive nearest-downbeat logic. Finds first downbeat ≥ `(t - tolerance)` but only snaps if within `fallback_threshold` (0.5s). Falls back to raw ChordMini value when beat tracker has drifted.
- **Beat tracker drift** observed from ~88s onward in end_of_beginning — madmom DBN lost sync at a dynamic transition, shifting the downbeat grid by ~1.5 bars for the remainder of the track. Fallback handles this cleanly.
- Segment boundary offset (ChordMini vs madmom misalignment) reduced from ~20–400ms to ~0–20ms for well-tracked sections.

See `docs/analysis-findings.md` for full diagnosis and proposed GUI correction tool.

---

## [edit 2.4] — 2026-05-29 — Current best
**Track:** labour.mp3 (B minor, 83 BPM)
**Cut:** 51.15s – 89.01s (chorus body, 37.86s)

Two-layer ending with BPM-synced delay tail extending 5s past cut end.
- Layer 1 (dry): full body, 2s fade at the very end
- Layer 2 (wet): delay (1 beat @ 83 BPM) + hall reverb, fades in over 2s, fades out over tail
- Intro: 6s filter sweep (low→full open) + volume fade-in + hall reverb + 80ms silence pad
- Click fixes: warmup > 1 delay cycle (1.22s), micro-fades at both boundaries of ending_src
- Primitive used: `chain()` for intro and wet layer composition

**Known limitation:** relies on full mix (mono stem). Cleaner intro/outro would use separated stems — guitar loop for intro sweep, isolated vocals for ending layer.

---

## [edit 2.3] — two-layer mix, bell-curve wet envelope
- Dry fades 1→0 over last 5s, wet fades 0→peak→0 (bell curve)
- Wet still ended at CUT_END — no tail extension
- Issue: bell curve ended too abruptly, no delay ring-out

## [edit 2.2] — two-layer ending, first working version
- Dry fades out, wet (delay+reverb) runs underneath
- Issue: delay time not BPM-synced, hard cut at layer boundary

## [edit 2.1] — ending zone with filter close + delay + fade
- Last 5s: half-beat delay → filter sweep close (full→300Hz) → fade out
- Issue: hard join between body and ending zone, felt forced

---

## [edit 1.5] — intro with hall reverb  *(split from 1.4 for preservation)*
- Adds reverb(wetness=0.5, hall) after filter sweep
- Initial click fix: fade applied before reverb, 80ms silence prepended
- Best non-layered version

## [edit 1.4] — filter sweep intro, no reverb
- 6s pre-roll: filter sweep open (220Hz→20kHz, curve=6) + fade(0.2→1.0)
- First clean sweep without click
- `filter_sweep` primitive with direction, freq_floor, freq_ceil, curve params

## [edit 1.3] — filter sweep with parametrized curve
- Introduced logarithmic frequency interpolation, curve parameter
- 1024-step zi carry-over approach — eliminated sweep clicks

## [edit 1.2] — filter sweep with separate volume fade
- Split `filter_sweep` (frequency only) from `fade` (volume only)
- User feedback: "fade in and out volume wise should be different thing"

## [edit 1.1] — first filter sweep
- Low-pass filter sweeps open from 100Hz to full over 6s
- `filter_sweep` primitive, scipy Butterworth, blend approach

## [edit 1.0] — basic cut
- User prompt: "keep only 0:51–1:29"
- Hard cut at 51.15s–89.01s, xfade join to main body
- Established: cut, xfade primitives

---

## Primitives developed this prototype phase

| Primitive | Signature | Description |
|-----------|-----------|-------------|
| `cut` | `cut(start, end)(audio)` | hard slice [start, end] in seconds |
| `fade` | `fade(vol_start, vol_end, curve)(audio)` | volume envelope, curves: linear/log/exp/qsin |
| `filter_sweep` | `filter_sweep(...)(audio)` | DJ-style low-pass sweep, direction + curve |
| `reverb` | `reverb(...)(audio)` | pedalboard Reverb, room/hall/plate presets |
| `delay` | `delay(...)(audio)` | pedalboard Delay, BPM-syncable |
| `xfade` | `xfade(xfade_ms)(a, b)` | equal-power crossfade join between two Audio clips |
| `chain` | `chain(audio, *transforms)` | compose curried primitives in sequence |

## Plan v2 devices (0.2.0, `src/recut/devices.py`)

Used from `plan.json` on clips, tracks, returns and the master, with automation of their parameters. The primitives above are the deprecated Python API.

| Device | Description |
|--------|-------------|
| `utility` | gain, width, mono |
| `eq` | low/high cuts (12 dB/oct), shelves |
| `auto_filter` | low/high/band-pass, 12 dB ladder with resonance |
| `reverb` | Freeverb, `decay` table, `dry_wet`, level-compensated |
| `delay` | BPM-synced, filters in the feedback loop |
| `limiter` | master limiter, true-peak aware (static trim to the ceiling) |
