# recut-prototype — Claude Instructions

## Project
Music cutting system ("Remotion for audio").
Analysis pipeline → JSON music map → primitives → LLM orchestration → specialized cutting model.

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
- `src/recut/primitives/` — pure numpy/pedalboard functions: cut, fade, filter_sweep, reverb, delay, xfade, chain
- `src/recut/map/` — map schema, make_map pipeline, chord data, ui-editor
- `src/recut/map/schema.py` — MusicMap dataclass + section/beat types
- `src/recut/map/parser.py` — JSON → MusicMap
- `src/recut/map/make_map.py` — analysis output → MusicMap
- `src/recut/validator/` — validation rules + checks
- `src/recut/compositor/` — compose() entry point, node types
- `src/analysis/pipeline.py` — Modal GPU pipeline for analysis
- `tests/` — map, primitives, validator test suites

## Primitives Interface
All primitives: `fn(audio: np.ndarray, sr: int, ...) → np.ndarray`
Use `chain(audio, sr, (fn, kwargs), ...)` to compose.

## Session Summaries
At the end of each working session (or when asked to wrap up), create `.claude/sessions/YYYY-MM-DD.md` covering:
- What was built or changed
- Key decisions and the reasoning behind them
- User instructions that shaped those decisions (verbatim or close paraphrase)
- Primitives added or modified
- Open threads / next steps

These summaries feed into the training dataset for the specialized cutting model — the user reasoning traces are as important as the code.
