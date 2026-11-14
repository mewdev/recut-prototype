> **⚠ Early prototype**: in active testing, formats and APIs may still change.

# recut

AI music editing, with recut doing for audio what Remotion does for video. A client sends a track and says what
they want ("make it 2:30, keep the second chorus, end on the real ending"). An agent
writes the edit as a small Ableton-style plan, recut renders it, and a human reviews it
in the browser. Every session is logged, so the system improves from the reviews.

```
track → analysis (Modal) → music map → agent writes plan.json → render + checks
      → browser review (per join: ok/bad, tags, note) → agent reworks → ship to client
                                         ↓
                weekly: recut report → improvement pass → general fixes (PR)
```

## Contents
- [Quick start](#quick-start)
- [Working with tickets](#working-with-tickets)
- [The weekly improvement pass](#the-weekly-improvement-pass)
- [Plan format](#plan-format)
- [Automatic checks](#automatic-checks)
- [CLI reference](#cli-reference)
- [Data layout](#data-layout)
- [Setup details](#setup-details) (Intel Mac, Modal, Docker)
- [Docs map](#docs-map)
- [Limitations](#limitations) · [Third-party models](#third-party-models) · [License](#license)

## Quick start

```bash
git clone https://github.com/mewdev/recut-prototype.git
git clone https://github.com/mewdev/recut-data.git        # private: ticket data, auto-saved
cd recut-prototype
conda create -n recut python=3.11 -y && conda activate recut
pip install -e ".[dev,qc]"          # Intel Mac: see "Setup details"

recut ticket demo                   # demo ticket from examples/summer-party, 2 cuts rendered
recut serve                         # → http://localhost:8000
```

In the browser:
- `space` plays and pauses.
- `a` switches between the cut and the original at the same musical position.
- `n` / `p` jump between joins, and `g` / `b` mark a join ok or bad.
- Pick a verdict, write a note and save.

Edit an iteration's `plan.json` and save it: the browser re-renders in about 0.1–0.5 s
and keeps playing from the same place.

## Working with tickets

A **ticket** is one client request: tracks plus text. Tickets are **data, not code**.
They live in `.appdata/tickets/`, which is git-ignored, and every attempt and review is
kept there.

```bash
recut ticket new song.mp3 --text "make it 2:30, end on the real ending" --duration 150
# `ticket new` first runs the intake check (`recut check-audio`) on every file and refuses blocking problems
# (low bitrate/bandwidth, short, ...) unless `--override`; the problems are kept in intake.json + the timeline.
recut ticket work <id> --model sonnet     # analyzes new tracks (Modal), starts a session, prints paths
```

1. **The agent cuts.** Open Claude Code in the repo and say *"Work ticket `<id>`
   following AGENTS.md"*. The agent writes `intent.json` (how it read the request), then
   `plan.json`, renders it, and puts each attempt in a new iteration.
2. **You review** at `recut serve` → `/t/<id>`:
   - Mark every join ok or bad, and tag the bad ones (`off_beat`, `fx_wrong`,
     `bad_ending`, …).
   - Pick a verdict:
     - **ship**: I'd send it exactly as it is
     - **fixable**: right direction, but I'd still change something
     - **reject**: wrong approach
   - Write what's wrong in plain words. The agent reads it.
3. **Fixable or reject** → run `recut ticket work <id>` again. The agent reworks from your
   review. **Ship** → click **Create client link** in the review panel (or
   `recut ticket share <id>`; base URL from `RECUT_PUBLIC_URL`) and send the link to the client.
   They listen (cut vs. original), approve or request changes, rate 1-5 and comment; the answer
   is logged automatically (every round is kept). If the client answers by email instead, log it
   by hand so approval rate and satisfaction can be reported (`recut report`, "Client feedback"):
   `recut ticket client <id> --approved --rating 4 --note "loved it"` or
   `recut ticket client <id> --changes --note "too long at the end"`. It attaches to the latest
   shipped iteration unless you pass `--session N --iteration K`. Log every round.

You create every ticket, with `recut ticket new` or the form at `/new` (operator-only). Clients never upload: they only open the share link, listen, and answer there.

**Transcript hook (once per machine).** It lets the improvement pass see the agent's
reasoning. See "Transcript hook" in [`AGENTS.md`](AGENTS.md).

## The weekly improvement pass

Run it every ~5–10 tickets. Code changes happen **only** here, and they must be
**general improvements, never per-ticket workarounds** (see the core principle in
[`AGENTS.md`](AGENTS.md)).

```bash
git checkout main && git pull && git checkout -b improve/2026-11-20
recut report --since 2026-11-13          # headline, turnaround, cost, baseline vs now, weekly trend; success rate, top failure tags, validator misses, worst sessions
claude                                   # use the strongest model (/model → Opus)
```

1. **Ask Claude Code to run the pass:** *"Run the weekly improvement pass following
   docs/IMPROVEMENT_LOOP.md on tickets since 2026-11-13."* It proposes the top 3 general
   fixes with evidence and waits for your OK.
2. **It implements the approved fixes with tests.** You push the branch and open a pull
   request.
3. **Review it in a fresh session** (`/code-review`), then merge it into `main`.

## Plan format

A plan is plain JSON, written like a small Ableton arrangement. The full spec is in
[`docs/PLAN.md`](docs/PLAN.md) §3.2.

- **Tracks** hold **clips**, which are chosen musically from the map: a `segment`, plus
  `bars` / `offset_bars` / `beats`, never timecodes.
- **Joins** are `xfade` entries with a `length` and a shape. `hold` keeps one side at full
  level.
- Clips have **gain** and **fade handles**.
- **Devices**: `eq`, `auto_filter`, `utility`, `reverb`, `delay`, `limiter`.
- Clips feed **sends** into **return tracks**, where reverb and delay live and ring out.
- **Automation** works as ramps or breakpoints.
- **Units:** time is written as `"1/8."`, `"2 bars"`, `"250ms"`; levels are in dB; mix
  and size settings are percentages, as Ableton shows them.

```python
from pathlib import Path

import soundfile as sf

from recut.contracts import Plan
from recut.engine import render_plan

plan = Plan.model_validate({
    "version": 2,
    "sources": {"a": {"file": "summer-party.mp3", "map": "summer-party-map.json"}},
    "returns": [{"id": "A", "name": "Reverb", "devices": [
        {"id": "lc", "type": "eq", "low_cut": 250},
        {"id": "verb", "type": "reverb", "decay": "2s", "pre_delay": "30ms", "dry_wet": 100}]}],
    "tracks": [{"id": "main", "clips": [
        {"id": "n1", "type": "clip", "source": "a", "segment": "intro",
         "fade_in": {"length": "1 beat", "shape": "linear"}},
        {"id": "n2", "type": "clip", "source": "a", "segment": "verse"},
        {"id": "n3", "type": "clip", "source": "a", "segment": "chorus", "bars": 4,
         "sends": {"A": -26},
         "automation": [{"target": "sends.A", "from": -26, "to": -13, "over": "2 bars", "at": "end"}]},
        {"id": "x1", "type": "xfade", "length": "30ms", "out_shape": "hold", "in_shape": "equal_power"},
        {"id": "n4", "type": "clip", "source": "a", "segment": "inst", "offset_bars": 4,
         "fade_out": {"length": "2 bars", "shape": "exp"}},
    ]}],
})

# intro → verse → half the chorus → the song's real ending, with a reverb wash into it
audio, info = render_plan(plan, Path("examples/summer-party"))
print(f"{info.duration_s:.1f}s", [f"{i.severity} {i.rule}" for i in info.issues])
sf.write("cut.wav", audio.samples.T, audio.sr)
```

`render_plan` returns the audio and a `RenderInfo`, which is what `render.json` holds:
segments, joins, issues, QC numbers and peak level. Recipes for common edits, like
endings and the "ending transplant", are in [`skills/cutting/`](skills/cutting/SKILL.md).

The older `Clip`/`XFade`/`compose()` Python API is deprecated but still works. To convert
old saved compositions, use `recut.legacy.composition_to_plan`.

## Automatic checks

Every render runs two kinds of checks. They show up in the browser's Problems panel and
in `render.json`.
- **Musical linter**, before rendering, on the plan and the map:
  - section and bar validity
  - `phrase_align`: joins should land on phrase boundaries
  - `ending`: the cut shouldn't stop mid-section without a fade
  - `energy_drop` across a join
  - `duration` against the target
- **Audio QC**, after rendering:
  - loudness compared with the source
  - limiter squash and true peak
  - clipping, clicks at joins, gaps
  - gain and brightness jumps at joins
  - low-quality source (bandwidth)
  - DC offset and phase

  Essentia's detectors are used where they're installed, except on Intel Macs (see
  below).

Joins you mark bad that no check flagged appear in `recut report` as **validator
misses**. Those are the input for new rules.

## CLI reference

```bash
# tickets
recut ticket new <files...> --text "..." [--duration S] [--override]   # create a ticket (intake check first)
recut check-audio <files...>                              # intake check only: bitrate, real bandwidth, length
recut ticket list                                         # all tickets + status
recut ticket work <id> [--model M]                        # analyze new tracks, start an agent session
recut ticket iterate <id>                                 # new attempt (copies the last plan)
recut ticket render <id> [--session N --iteration K]      # render + print issues
recut ticket client <id> (--approved | --changes) [--rating 1-5] [--note "..."] [--session N --iteration K]   # log the client's decision
recut ticket demo                                         # demo ticket from examples/summer-party
recut ticket import-legacy <export_dir> [--root DIR] [--force]  # pre-refactor session export → baseline ticket (agent legacy-pre-refactor)
recut serve [--port 8000]                                 # review server + live preview (operator page /report = live results page)
recut report [--since DATE] [--json | --html [--out FILE]]  # numbers for the improvement pass; --html = presentation page (recut-report.html)
recut sync                                                # commit + push ticket data to recut-data
recut ticket awaiting                                     # shipped cuts with no client feedback logged yet

# analysis + legacy compositions
recut analyze <track>        # Modal analysis → raw JSON
recut map                    # build enriched music maps
recut status                 # source registry
recut compositions | validate <name> | render <name>      # old compose() workflow
```

## Data layout

**Tickets are saved to the private data repo [`mewdev/recut-data`](https://github.com/mewdev/recut-data)**
when it's cloned next to this repo (`git clone https://github.com/mewdev/recut-data.git`
in the same parent folder). Every ticket action is then committed and pushed
automatically, from the CLI, the review server and the transcript hook alike. Audio is
never committed. `recut serve` shows `data repo: … (auto-sync on)`. Use `recut sync` to
sync by hand, `RECUT_AUTOSYNC=0` to turn it off, and `RECUT_TICKETS_DIR=/path` to put
tickets elsewhere. Without a data repo, tickets stay local in `.appdata/tickets/`.

Everything else recut generates (analysis, legacy compositions) lives in `.appdata/` in
the repo folder. Set `RECUT_HOME=/some/folder` to use `/some/folder/.appdata/`.

```
recut-data/tickets/<id>/            (or .appdata/tickets/<id>/ without a data repo)
  request.json                       client text, target duration, files, status
  inputs/<a|b|…>.<ext>  maps/<a|b|…>.json
  sessions/<n>/meta.json             agent, model, git sha
  sessions/<n>/intent.json           how the agent read the request
  sessions/<n>/events.jsonl          every render + review, failures included
  sessions/<n>/transcript.jsonl      agent transcript (hook)
  sessions/<n>/iterations/<k>/       plan.json  render.json  audio.wav  review.json
.appdata/audio/  maps/  compositions/  renders/    (analysis + legacy compose workflow)
```

## Setup details

**Python:** use 3.10 or 3.11. `pip install -e ".[dev]"` adds the test tools, and `[qc]`
adds Essentia.

**Intel Mac:**
- Some dependencies no longer ship Intel builds. Install with
  `pip install --only-binary=llvmlite,numba,cbor2 -e ".[dev,qc]"`, so pip picks versions
  that have ready-made Intel packages instead of compiling (which needs CMake and Rust).
- Essentia's Intel build crashes Python on import ("Failed loading SDL2 library").
  recut skips it on Intel Macs automatically, and QC uses its basic detectors. If it got
  installed anyway: `pip uninstall -y essentia`.

**Modal (track analysis).** You need a [Modal account](https://modal.com); the free tier
is enough.
```bash
modal token new                          # one-time login, saves ~/.modal.toml
modal deploy src/analysis/pipeline.py    # models are fetched at deploy time
```

**Docker.** One image runs on Mac (Docker Desktop), Linux and a VPS. Create
`~/.modal.toml` first, because compose mounts it.
```bash
docker compose up -d --build
docker compose exec recut recut ticket demo     # then http://localhost:8000
docker compose run --rm recut python -m pytest tests/ -q
```

**Before every commit:** `ruff check .` and `python -m pytest tests/`.

## Docs map

| File | What it's for |
|---|---|
| [`AGENTS.md`](AGENTS.md) (= `CLAUDE.md`) | Rules for every agent: core principle, ticket workflow, transcript hook |
| [`docs/PLAN.md`](docs/PLAN.md) | Decisions and the frozen formats (plan, render, tickets, API) |
| [`docs/STATUS.md`](docs/STATUS.md) | Task table, decisions, blockers, handoff log |
| [`docs/IMPROVEMENT_LOOP.md`](docs/IMPROVEMENT_LOOP.md) | How session data becomes general fixes |
| [`docs/workstreams/`](docs/workstreams/) | Task briefs per area: engine, backend, frontend, quality, music data |
| [`skills/`](skills/) | Agent skills: `cutting` (writing plans, recipes) and `music-theory` (judgment) |

## Limitations

Full list in [`LIMITATIONS.md`](LIMITATIONS.md). The main ones:
- **One track per plan.** Sequencing several songs works; layering (mashups) and stems
  don't yet.
- **No time-stretching.** Joins between songs need compatible tempos.
- **Basic reverb.** It's an algorithmic room; a convolution reverb is a candidate task.
- **The map has no drum/vocal activity or pace yet.** This is planned in
  `docs/workstreams/M-music-data.md`.
- **Meter detection** covers 3/4 and 4/4 only.

## Third-party models

The analysis models are fetched automatically by `modal deploy`.

| Component | Source | License |
|-----------|--------|---------|
| **madmom** (beat tracking) | [CPJKU/madmom](https://github.com/CPJKU/madmom) | BSD-3-Clause ✅ |
| **Chord-CNN-LSTM** (chord recognition) | [ptnghia-j/chord-cnn-lstm-model](https://github.com/ptnghia-j/chord-cnn-lstm-model), a fork of [music-x-lab/ISMIR2019](https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition) | MIT ✅ |
| **SongFormer** (structure segmentation) | [ASLP-lab/SongFormer](https://github.com/ASLP-lab/SongFormer) via [mewdev/ChordMiniApp](https://github.com/mewdev/ChordMiniApp) | MIT ✅ |
| **MusicFM** weights | [minzwon/MusicFM](https://huggingface.co/minzwon/MusicFM) | MIT ✅ |
| **MuQ** weights | [OpenMuQ/MuQ-large-msd-iter](https://huggingface.co/OpenMuQ/MuQ-large-msd-iter) | CC BY-NC 4.0 ⚠ |
| **Essentia** (key detection; QC detectors) | [MTG/essentia](https://github.com/MTG/essentia) | AGPLv3 ⚠ |
| **pyloudnorm** (QC loudness) | [csteinmetz1/pyloudnorm](https://github.com/csteinmetz1/pyloudnorm) | MIT ✅ |

> **⚠ Non-commercial prototype.** MuQ is CC BY-NC (non-commercial). SongFormer uses it,
> so the structure analysis is non-commercial too. Essentia is AGPLv3, and that copyleft
> covers network/SaaS use as well. Before any commercial or hosted use:
> - replace MuQ (e.g. with MERT or EnCodec)
> - replace Essentia key detection
> - remove `src/recut/qc_essentia.py`

## Inspiration

**[Remotion](https://www.remotion.dev)**: declarative, code-driven video editing. recut
applies the same model to audio.

**[VideoAgent](https://github.com/HKUDS/VideoAgent)**: an LLM agent that orchestrates
video editing through tool use over media primitives.

## License

recut's own code is [MIT licensed](LICENSE). The third-party models it uses for analysis
have their own licenses; see the table above before any commercial use.

## Presenting results

`recut report --html` writes one self-contained page (`recut-report.html`: inline CSS and SVG, no network
requests, light/dark, phone-friendly): headline tiles, weekly trend, review rounds, top failure tags, a few client
quotes, baseline vs ticket system. `recut serve` shows the same page live at `/report` (operator-only). Demo
tickets are never counted, every rate shows its n, metrics with n < 5 say "too few to judge", costs are
API-equivalent estimates (not invoices), and nothing is extrapolated.
