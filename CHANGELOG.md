# Changelog

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

| Primitive | Description |
|-----------|-------------|
| `cut` | hard slice [start, end] in seconds |
| `fade` | linear volume envelope |
| `filter_sweep` | DJ-style low-pass sweep, direction + curve |
| `reverb` | pedalboard Reverb, room/hall/plate presets |
| `delay` | pedalboard Delay, BPM-syncable |
| `xfade_join` | equal-power crossfade join between two segments |
| `chain` | compose effects: `chain(audio, sr, (fn, kwargs), ...)` |
