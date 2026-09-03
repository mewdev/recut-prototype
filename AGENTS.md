# recut-prototype — Agent Instructions

Music cutting system ("Remotion for audio"): analysis pipeline → JSON music map → primitives → LLM orchestration → specialized cutting model.

## Cutting or editing an audio track

If the request is to trim, cut, loop, crossfade, or otherwise edit an existing song via the recut framework, use the `cutting` skill (`skills/cutting/SKILL.md`) — it covers the `Clip`/`XFade`/`compose()`/`validate()` API and the CLI. Pair it with the `music-theory` skill (`skills/music-theory/SKILL.md`) for musical judgment (hook selection, cadence quality, energy arcs).

If your harness doesn't auto-discover skills from `.claude/skills/`, load those two `SKILL.md` files directly — they're plain markdown with no Claude-Code-specific mechanics beyond the YAML frontmatter.

Not covered by either skill: composing new melodies/lyrics/orchestration (out of scope), or generating/enriching a music map (`recut analyze` / `recut map`, `src/analysis/`, `src/recut/map/make_map.py`).

## Python Environment
Always use `/Users/michal/miniconda3/envs/recut/bin/python` — never `conda run -n recut` (picks up wrong system Python).

## Before Every Commit
Run both — fix all errors before committing:
```
/Users/michal/miniconda3/envs/recut/bin/ruff check .
/Users/michal/miniconda3/envs/recut/bin/python -m pytest tests/
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
