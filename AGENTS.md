# recut-prototype — Agent Instructions

Music cutting system ("Remotion for audio"): analysis pipeline → JSON music map → primitives → LLM orchestration → specialized cutting model.

## Building the prototype (week 1): start here

If you were given a build task (an ID like A3, B2 or C5), read these in order and nothing else unless the task needs it:
1. `docs/PLAN.md`: decisions (§2) and **contracts (§3), which are frozen**
2. `docs/workstreams/<A-engine|B-backend|C-frontend|Q-quality|M-music-data>.md`: your task list, the files you own, and what you must not touch
3. `docs/STATUS.md`: current state, blockers, and the handoff log

Rules:
- Do **one task**, make its *Done when* check pass, update `docs/STATUS.md`, then commit.
- Never edit files outside your workstream. Never change `src/recut/contracts/`.
- Weekly improvement pass (turning session data into fixes): follow `docs/IMPROVEMENT_LOOP.md`.
- If something is unclear, **don't guess**: write it under *Blockers* in `docs/STATUS.md` and stop or move to the next task.

## Working a client ticket (cutting agents)

Tickets live in `.appdata/tickets/<id>/` (format: `docs/PLAN.md` §3). To work one:
1. `recut ticket work <id> --model <your model>` starts a session (it analyzes unmapped
   tracks via Modal) and prints the paths.
2. Read `request.json` and the previous session's `review.json` if there is one: its
   per-splice tags and note are what to fix.
3. Write `intent.json` (how you read the request) **before** cutting.
4. Edit the iteration's `plan.json` (§3.2: sections + bars/beats, Ableton-style units).
   `recut ticket render <id>` renders it and prints issues; with `recut serve` running,
   the operator's browser updates live.
5. For a new attempt, run `recut ticket iterate <id>` instead of overwriting: every
   attempt is kept, failures included.

The `cutting`/`music-theory` skills below give the musical judgment. `skills/cutting/` is
written for `plan.json` (the ending-transplant recipes are in
`skills/cutting/references/ending-transplant.md`); its `api-reference.md` documents the
deprecated Python API only.

## Cutting or editing an audio track

If the request is to trim, cut, loop, crossfade, or otherwise edit an existing song via the recut framework, use the `cutting` skill (`skills/cutting/SKILL.md`) — it covers writing a plan (clips, joins, devices, sends, automation) and the CLI. Pair it with the `music-theory` skill (`skills/music-theory/SKILL.md`) for musical judgment (hook selection, cadence quality, energy arcs).

If your harness doesn't auto-discover skills from `.claude/skills/`, load those two `SKILL.md` files directly — they're plain markdown with no Claude-Code-specific mechanics beyond the YAML frontmatter.

Not covered by either skill: composing new melodies/lyrics/orchestration (out of scope), or generating/enriching a music map (`recut analyze` / `recut map`, `src/analysis/`, `src/recut/map/make_map.py`).

## Python Environment
Use the `recut` environment's Python directly, never `conda run -n recut` (it picks up the
wrong system Python). On the operator's Mac that's
`/Users/michal/miniconda3/envs/recut/bin/python`. In other environments (cloud sessions,
CI), use the Python where `pip install -e ".[dev]"` was run.

## Before Every Commit
Run both and fix all errors before committing (with the environment's `ruff`/`python`):
```
ruff check .
python -m pytest tests/
```

## Key Files
- `CHANGELOG.md` — version history + primitives table
- `src/recut/primitives/` — curried functions: cut, fade, filter_sweep, reverb, delay, xfade, chain; shared envelope curves in `curves.py`
- `src/recut/map/` — map schema, make_map pipeline, chord data
- `src/recut/map/schema.py` — MusicMap (Pydantic BaseModel) + section/beat types
- `src/recut/map/parser.py` — JSON → MusicMap
- `src/recut/map/make_map.py` — analysis output → MusicMap
- `src/recut/validator/` — validation rules + checks
- `src/recut/compositor/` — compose() entry point, node types
- `src/recut/project.py` — source registry (.appdata scan, status classification, hash verify) + composition registry (save/load/list edit plans)
- `src/recut/paths.py` — `.appdata/` layout: audio/, maps/raw/, maps/enriched/, compositions/, renders/
- `src/analysis/pipeline.py` — Modal GPU pipeline for analysis
- `tests/` — map, primitives, validator, compositor, cli, project, skills test suites

## Primitives Interface
All primitives are curried closures: `fn(**params) -> (audio: Audio) -> Audio`. Compose with `chain(audio, fade(...), reverb(...), ...)` — bare callables passed positionally.

## Skills
- `skills/cutting/` — build and render edits (see above)
- `skills/music-theory/` — musical judgment for cutting decisions (see above)
