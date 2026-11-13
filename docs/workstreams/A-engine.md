# Workstream A — Engine (multi-source compose, render.json, validator, logging)

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
`recut.contracts`). Also write `to_nodes(plan) -> list[Clip | XFade]` for the single lane.
`Clip.source` gets the plan's source id.
- Raise `ValueError("multi-lane not supported yet")` if there's more than one lane.
- Done when: `pytest tests/plan -q` passes. Write the tests: a round trip of
  `tests/fixtures/tickets/medley-demo/.../plan.json`, plus the multi-lane error.

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

### A7 — Timeline compose: overlaps, ring-out, scoped effects (ending transplant)
This is the operator's most common manual fix (PLAN §2 "Ending transplant"). Change `compose()` so it
**places clips on a timeline buffer and adds up overlaps**, instead of concatenating them.
Then add these plan fields (PLAN §3.2):
- `XFade.out_curve` / `in_curve`, which default to `curve`. `"hold"` means full volume for
  the whole overlap.
- `Clip.ring_out`: pad the clip for its effect tail (reuse `_reverb_tail_padding`, which
  today only applies to the **last** clip), and mix the tail under the following
  material.
- `Effect.scope = {"last_beats": n} | {"first_beats": n}`: apply the effect only to that
  part, with a 20 ms equal-power blend at the scope edge so nothing clicks. Closes issue
  #53.
- Master limiter (`pedalboard.Limiter`), applied only if the peak exceeds -1 dBFS. Set
  `render.json.peak_dbfs` and `limiter_applied`.
- New validator rule `peak_clip` (warn): the summed peak before the limiter is above
  0 dBFS.
- `render.json` splices report `overlap_ms`, `out_curve`, `in_curve`, `ring_out_ms`.

Then add the recipe `skills/cutting/references/ending-transplant.md` with the three
variants the operator uses, each as a plan.json snippet:
1. hit on top + tail rings (`ring_out` on the previous clip, short `xfade`, `in_curve: "hold"`)
2. reverb wash into the ending (`reverb` scoped `last_beats: 1–2` + `ring_out`)
3. normal crossfade + reverb on the ending clip

Link the recipe from `skills/cutting/SKILL.md` step 6 and from
`references/exit-design.md`.
- Done when:
  - all existing tests pass unchanged (plain concatenation and xfade output stay within
    1e-6 of today's)
  - new tests cover: `hold` overlap length, ring-out tail energy after the splice > 0,
    a scoped effect leaving the earlier samples untouched, the limiter only kicking in
    when the peak is too high
  - the fixture's ending-transplant plan renders without clicks (no sample-to-sample
    jump > 0.5)
- Model: Sonnet. Do it after A4 (it changes what A4 reports).

## Out of scope
Multi-lane mixing, stem separation and time-stretch (week 2). Don't start them.
