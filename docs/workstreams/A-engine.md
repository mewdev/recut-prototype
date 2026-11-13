# Workstream A — Engine (multi-source compose, render.json, validator, logging)

**State after D1 + thin slice (2026-11-13):** `src/recut/engine.py` renders plan v2 on a
timeline (sources, one track, clip selection/loop/gain/fade handles, xfade incl. `hold`,
master limiter) and writes `render.json`. A1, A2 and A4 are **done** there. Extend
`engine.py` for A3/A5/A7/A8; don't build a second renderer in `compositor/`. Features
not rendered yet show up as `not_rendered` warnings in `render.json`; remove each warning
when you implement the feature.

**Read first:** `AGENTS.md` → `docs/PLAN.md` §3 (contracts) → this file → `docs/STATUS.md`.
**Owns:** `src/recut/` except `src/recut/server/` and `src/recut/contracts/`.
**Does not touch:** `src/recut/contracts/` (frozen; if you need a change, add it to *Blockers* in
`docs/STATUS.md` and stop), `src/recut/server/`, `web/`.
**Suggested model:** Sonnet. Tasks A1, A6 are fine for Haiku.

Work the tasks **in order**. Each task is done only when its **Done when** command passes
and you have added a line to `docs/STATUS.md`. Commit after each task (see AGENTS.md
"Before Every Commit").

## Tasks

### A1 — Plan v2 → nodes
Write `recut.plan.load_plan(path) -> PlanV2`, which reads `plan.json` (schema in
`recut.contracts`). It resolves every time and level string through `recut.contracts.units`, so `"1/8."` and `"-inf"` are checked when the plan loads, not at render time.
`Clip.source` gets the plan's source id.
- Raise `ValueError("multi-track not supported yet")` if there's more than one track.
- Done when: `pytest tests/plan -q` passes. Write the tests: a round trip of
  `tests/fixtures/tickets/medley-demo/.../plan.json`, plus the multi-track error and a bad unit string (`"1/7"`) rejected with a clear message.

### A2 — Multi-source compose
Change `compose()` to accept `sources: dict[str, tuple[MusicMap, Audio]]` and resolve
each `Clip.source` against it.
- Keep the old signature `compose(music_map, audio, *nodes)` working: it's treated as a
  single source named `"default"`.
- If two sources have different sample rates, resample to the first source's rate.
- Done when: the existing tests pass, plus a new test that composes a 2-source medley
  from the fixture.

### A3 — LUFS match
On load, normalise every source to `-14 LUFS` integrated (`pyloudnorm`; add it to
`pyproject.toml`). Store `lufs_in` and `lufs_target` for each source.
- Done when: a test shows two sources with a ≥6 dB level difference come out within
  1 LU of each other.

### A4 — render.json
`compose()` also returns a `RenderInfo` (in `recut.contracts`) holding `segments`,
`splices` and `sources`, with the times it actually rendered.
- Account for crossfade overlap: `out_start` of the clip after an XFade is earlier.
- `splice.id`: `s1`, `s2`, … in timeline order. `cross_source` is true if `from` and
  `to` use different sources.
- Done when: a test checks the fixture medley's segments and splices against the
  expected values in `tests/fixtures/tickets/medley-demo/expected_render.json`, with a
  tolerance of 10 ms.

### A5 — Cross-song validator rules
Add these to `src/recut/validator/rules.py`, all keyed by splice id:

| rule | severity | condition |
|---|---|---|
| `downbeat` | error | splice point isn't within 30 ms of a downbeat in **each** source's beat grid (use beats, not segment boundaries) |
| `bpm_gap` | warn | tempo differs by >3% and isn't within 3% of a 2:1 ratio |
| `key_compat` | warn | keys aren't the same, relative, or ±1 on the Camelot wheel |
| `loudness_jump` | warn | short-term loudness (3 s window) jumps >3 dB across the splice |

- Done when: each rule has one passing test and one failing test.

### A6 — Session logging
If env `RECUT_SESSION` is set, `compose`, `validate` and the CLI `render` each append one
line to `$RECUT_SESSION/events.jsonl`:
`{ts, op, plan_hash, duration_ms, issues, error}`.
- Logging must never crash the caller: catch errors and warn instead.
- Done when: a test with `tmp_path` checks the lines are written, and a test with the env
  unset checks nothing is written.

### A7 — Timeline engine: tracks, joins, returns/sends, master (ending transplant core)
This is the operator's most common manual fix (PLAN §2 "Ending transplant") and the
engine half of the Ableton-style model (PLAN §3.2). Do it after A4 (it changes what A4
reports).
- `compose()` **places clips on a timeline buffer and adds up overlaps**, instead of
  concatenating them.
- Clip `gain` and `fade_in`/`fade_out` handles.
- `xfade` with `length` + `shape`, or `out_shape`/`in_shape` (`hold` = full level for
  the whole overlap).
- **Return tracks:** each clip's `sends` (dB) feed a timeline-length send buffer for each
  return. The return's device chain runs once over that buffer, and the result is added
  to the mix. Extend the output so the return tails can die out (stop at -60 dB or at
  10 s at most), then set `returns_tail_end`.
- Track `volume`/`pan`, then the master chain. The default master is a `limiter` at -1 dB
  ceiling, and `render.json` gets `peak_dbfs` and `limiter_applied`.
- New validator rule `peak_clip` (warn): the summed peak before the master chain is above
  0 dBFS.
- `render.json` splices report `overlap_ms`, `out_shape`, `in_shape`.
- The Python API mirrors the JSON names, so code reads like the plan:
  `Clip("verse", index=2, bars=4, gain=-1.5, sends={"A": "-inf"}, fade_out=Fade("2 bars", "exp"))`,
  `XFade("30ms", out_shape="hold")`.
- Done when:
  - existing tests pass. A plain concatenation or a symmetric xfade plan must produce
    the same samples as today (within 1e-6), going through the old-format adapter
    (A8) or a direct equivalent.
  - new tests cover: `hold` overlap length; a send opened on the last beat leaving return
    energy after the clip ends (> -40 dB for 1 s); the limiter only applied when the
    peak is too high
  - the fixture's ending-transplant plan renders without clicks: no sample-to-sample jump
    within ±5 ms of a splice larger than the source's own largest jump (music has sharp
    transients, so an absolute threshold doesn't work; see `tests/engine/test_engine.py`)
- Model: Sonnet.

### A8 — Devices, automation, old-format adapter, skill docs
- Devices with Ableton parameter names, as in the PLAN §3.2 table:
  - `utility`, `eq` (pedalboard HighpassFilter/LowpassFilter/PeakFilter), `auto_filter`
  - `reverb`: pedalboard Reverb plus a pre-delay line and a hi-cut. Map `decay` to room
    size with a documented table.
  - `delay`: tempo-synced `time`, `ping_pong`, filters
  - `limiter`
- **Automation engine:** ramps and points become a per-sample parameter curve. Gain and
  send levels are applied per sample. For device parameters that pedalboard can't change
  per sample, process in blocks of ≤ 512 samples with the parameter updated per block
  (the same approach `reverb_sweep` uses today; reuse it).
- **Old-format adapter:** saved compositions that use `Fade`, `Reverb`, `ReverbSweep`,
  `Delay`, `FilterSweep` or `XFade(ms, curve)` load into the new model. `qsin` maps to
  `equal_power`, and `vol_*` values convert linear → dB. Mark the old classes deprecated
  but keep them working.
- **Skill docs:** rewrite `skills/cutting/SKILL.md` and
  `references/effects-cheatsheet.md` in the new vocabulary. Add
  `references/ending-transplant.md` with the operator's three variants as `plan.json`
  snippets:
  1. hit on top + tail rings: send open on the outgoing clip, short `xfade` with
     `in_shape: "hold"`
  2. reverb wash into the ending: `sends.A` ramp `-inf → 0` over the last 1–2 beats
     `at: "end"`
  3. normal crossfade + reverb on a return
  
  Link the recipe from SKILL.md step 6 and `references/exit-design.md`. Update
  `README.md`'s code example.
- Done when:
  - `pytest tests/ -q` passes, including `tests/skills`
  - every device has a test checking its parameters have an audible, correctly signed
    effect (e.g. `auto_filter` lowpass at 500 Hz reduces energy above 2 kHz by > 12 dB)
  - one test loads each old-format effect through the adapter
- Model: Sonnet. Do it after A7.

## Out of scope
Multi-track mixing, stem separation and time-stretch (week 2). Don't start them.
