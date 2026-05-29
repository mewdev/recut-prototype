# recut-prototype — Claude Instructions

## Project
Music cutting system ("Remotion for audio"). See `music-cutting-system-plan.md` for full architecture.
Analysis pipeline → JSON music map → primitives → LLM orchestration → specialized cutting model.

## Python Environment
Always use `/Users/michal/miniconda3/envs/recut/bin/python` — never `conda run -n recut` (picks up wrong system Python).

## Key Files
- `music-cutting-system-plan.md` — architecture plan
- `CHANGELOG.md` — edit version history + primitives table
- `docs/use-cases/` — training triplets (music_map + instruction + correct_edit + reasoning)
- `testing/01/labour-full.json` — merged analysis output for labour.mp3
- `primitives/` — pure numpy/pedalboard functions: cut, fade, filter_sweep, reverb, delay, xfade_join, chain
- `modal_pipeline.py` — Modal GPU pipeline for allin1 analysis
- `todo-and-ideas.md` — backlog

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
