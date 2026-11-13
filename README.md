> **⚠ Early prototype / MVP** — work in progress, APIs may change.

# recut

Declarative audio editing — describe music edits in code, recut renders them.

The system analyzes an audio file into a structured music map (segments, beats, chords), then lets you compose edits programmatically using a simple node-based API.

```
audio → analyze → music map → compose edits → output audio
```

## Setup

**1. Create and activate the conda environment**
```bash
conda create -n recut python=3.10
conda activate recut
```

**2. Install recut and its dependencies**
```bash
pip install -e .
```

Use `pip install -e ".[dev]"` to also get the test tools (pytest, ruff, httpx).

**Intel Mac notes:**
- Some dependencies no longer ship Intel-Mac packages. Install with
  `pip install --only-binary=llvmlite,numba,cbor2 -e ".[dev,qc]"`, so pip picks the
  newest versions that still have ready-made Intel builds instead of compiling (which
  needs CMake/Rust).
- Essentia's Intel-Mac build crashes Python on import ("Failed loading SDL2 library").
  The `qc` extra skips it on Intel Macs, and QC uses its basic detectors there. If you
  installed it already: `pip uninstall -y essentia`.

**Try the review GUI (no Modal needed):**
```bash
recut ticket demo     # demo ticket from examples/summer-party, 2 rendered iterations
recut serve           # → http://localhost:8000
```
Edit a `plan.json` under `.appdata/tickets/<id>/sessions/1/iterations/2/` and the browser
re-renders and reloads at the same playhead. Workflow and formats: `docs/PLAN.md`.

**3. Set up Modal (for audio analysis)**

Requires a [Modal account](https://modal.com) — free tier is sufficient.

```bash
pip install modal
modal token new       # one-time authentication, saves to ~/.modal.toml
modal deploy src/analysis/pipeline.py
```

Models are cloned automatically at deploy time — no manual download needed.

## Run with Docker

One image runs on Intel Mac (Docker Desktop), Arch Linux, and the VPS. Create `~/.modal.toml`
first (step 3 above); the compose file mounts it so `recut ticket work` can run analysis on Modal.

```bash
docker compose up -d                                # build and start the review server
docker compose exec recut recut ticket demo         # create the demo ticket
# then open http://localhost:8000
```

Tickets and renders are stored in `./.appdata` on the host. The container restarts unless stopped.
To run the tests inside the image: `docker compose run --rm recut python -m pytest tests/ -q`.

## CLI

```bash
# Analyze an audio file → raw JSON (also copies the audio into .appdata/audio/)
recut analyze path/to/track.mp3

# Build enriched music maps for all sources that need one
recut map

# Registry state for all sources (ready / needs_map / needs_analysis / hash_mismatch)
recut status

# List saved compositions
recut compositions

# Validate a saved composition against its music map
recut validate <name>

# Validate, then render a saved composition to audio (--force skips validation errors, --out sets the path)
recut render <name>

# Help
recut --help
recut analyze --help
```

Everything recut generates lives in `.appdata/` (git-ignored) **in the repo folder**, wherever you run `recut` from. Set `RECUT_HOME=/some/folder` to keep it elsewhere (`$RECUT_HOME/.appdata/`):
- `.appdata/audio/<stem>.mp3` — source audio, copied in by `analyze`
- `.appdata/maps/raw/<stem>.json` — raw model output (beats, chords, structure)
- `.appdata/maps/enriched/<stem>.json` — enriched music map
- `.appdata/compositions/<name>.json` — saved edit plans
- `.appdata/renders/<name>.mp3` — rendered output from `recut render`

**Try it without your own Modal deploy**: `examples/summer-party/` has a
pre-analyzed track (audio + enriched map) — copy it into `.appdata/` per that
folder's README and skip straight to the code example below.

## Code Example

Given an analyzed track (the bundled `examples/summer-party/` works here — see Setup
above), build a cut in code:

```python
from pathlib import Path

import soundfile as sf

from recut.contracts import Plan
from recut.engine import render_plan

# A plan is plain data: sources, one track of clips and joins, returns (reverb/delay),
# devices and automation. Format: docs/PLAN.md section 3.2.
plan = Plan.model_validate({
    "version": 2,
    "sources": {"a": {"file": "audio/summer-party.mp3", "map": "maps/enriched/summer-party.json"}},
    "returns": [{"id": "A", "name": "Reverb", "devices": [
        {"id": "verb", "type": "reverb", "decay": "3.5s", "pre_delay": "20ms", "dry_wet": 100}]}],
    "tracks": [{"id": "main", "clips": [
        {"id": "n1", "type": "clip", "source": "a", "segment": "chorus"},
        {"id": "n2", "type": "clip", "source": "a", "segment": "intro"},
        {"id": "x1", "type": "xfade", "length": "2 beats", "shape": "equal_power"},
        {"id": "n3", "type": "clip", "source": "a", "segment": "verse"},
        {"id": "n4", "type": "clip", "source": "a", "segment": "inst", "bars": 7},
        {"id": "x2", "type": "xfade", "length": "30ms", "out_shape": "hold", "in_shape": "equal_power"},
        {"id": "n5", "type": "clip", "source": "a", "segment": "inst", "offset_bars": 7,
         "sends": {"A": -6}, "fade_out": {"length": "2 bars", "shape": "exp"}},
    ]}],
})

# chorus (hook) -> intro -> verse -> inst, fading out over the last bars with the reverb ringing on
audio, info = render_plan(plan, Path(".appdata"))
print(info.duration_s, info.peak_dbfs, [i.message for i in info.issues])

sf.write("summer-party-cut.wav", audio.samples.T, audio.sr)
```

`render_plan` returns the audio and a `RenderInfo` (what `render.json` holds: segments, splices,
issues, return tail end, peak level). Clips are chosen musically from the map (`segment`, `bars`,
`offset_bars`), never by timecodes. Reverb and delay sit on **return tracks** that clips feed with
`sends`; `devices` (`eq`, `auto_filter`, `utility`, `reverb`, `delay`, `limiter`) and `automation`
use Ableton's names and units (`"1/8."`, `"2 bars"`, dB, percentages). `recut ticket render <id>`
does the same for a ticket's `plan.json` and prints the issues.

The older `Clip`/`XFade`/`compose()` Python API and its `Fade`/`Reverb`/`Delay`/`FilterSweep` effects
still work but are deprecated; old saved compositions convert to a plan with
`recut.legacy.composition_to_plan`.

**Validation** — a linter for music cuts. Before rendering, validates that all nodes are musically coherent: segment labels exist in the map, requested bars/beats don't exceed the segment duration, and the cut doesn't start or end abruptly mid-song. The goal is to grow this into a richer rule set that catches musical issues automatically — wrong key transitions, energy drops, rhythmic misalignments — so the system can eventually guide or automate cut decisions.

```python
from recut.validator import validate

issues = validate(music_map, Clip("intro"), Clip("verse"), Clip("chorus", loop=2))
# issues: list of ValidationResult with severity ("error" | "warning") and message
```

The analysis extracts tempo, time signature, song structure, beats, chords, and loudness — everything needed to make musically aware cuts.

## Agent / Harness Usage

recut ships two [Agent Skills](https://code.claude.com/docs/en/skills) at `skills/cutting/` and `skills/music-theory/` — `cutting` covers writing a plan (tracks, clips, devices, sends, automation) and the ending-transplant recipes, `music-theory` covers the musical judgment behind a cut (cadence quality, hook selection, energy arcs). Point your harness at both; currently tested with Claude Code.

## Current Limitations

recut is an early prototype. A few headline gaps — full list in [`LIMITATIONS.md`](LIMITATIONS.md):

- One track only — sequencing several songs works, layering (mashups) doesn't yet.
- No time-stretching — pick joins between songs with compatible tempos.
- No live per-instrument/stem editing — clips are full mixes.
- Musical judgment (cadence quality, hook selection) is inferred by whoever's reasoning about the cut, not verified against ground-truth data — the map has no harmonic-function or cadence fields.
- Meter detection covers 3/4 and 4/4 only.

## Third-Party Models

recut currently uses third-party open-source models for music analysis. All models are cloned automatically when you run `modal deploy`. No manual setup required.

| Component | Source | License |
|-----------|--------|---------|
| **madmom** (beat tracking) | [CPJKU/madmom](https://github.com/CPJKU/madmom) | BSD-3-Clause ✅ |
| **Chord-CNN-LSTM** (chord recognition) | [ptnghia-j/chord-cnn-lstm-model](https://github.com/ptnghia-j/chord-cnn-lstm-model) — fork of [music-x-lab/ISMIR2019](https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition) | MIT ✅ |
| **SongFormer** (structure segmentation) | [ASLP-lab/SongFormer](https://github.com/ASLP-lab/SongFormer) via [mewdev/ChordMiniApp](https://github.com/mewdev/ChordMiniApp) | MIT ✅ |
| **MusicFM** weights | [minzwon/MusicFM](https://huggingface.co/minzwon/MusicFM) | MIT ✅ |
| **MuQ** weights | [OpenMuQ/MuQ-large-msd-iter](https://huggingface.co/OpenMuQ/MuQ-large-msd-iter) | CC BY-NC 4.0 ⚠ |
| **Essentia** (key detection) | [MTG/essentia](https://github.com/MTG/essentia) | AGPLv3 ⚠ |

> **⚠ MuQ is non-commercial only** (CC BY-NC 4.0, Tencent AI Lab). SongFormer uses MuQ as its audio encoder, making the structure pipeline non-commercial. Replace MuQ with a MIT-licensed alternative (MERT, EnCodec) before any commercial use.

> **⚠ Essentia is AGPLv3** (free for non-commercial use; a separate commercial license is required otherwise — [MTG/UPF](https://essentia.upf.edu/)). AGPL's copyleft extends to network/SaaS use, not just redistribution — a stronger constraint than MuQ's non-commercial clause. Replace with a permissively-licensed key-detection method before any commercial or hosted use.

## Inspiration

**[Remotion](https://www.remotion.dev)** — declarative, code-driven video editing; recut's core model, applied to audio instead.

**[VideoAgent](https://github.com/HKUDS/VideoAgent)** — LLM agent orchestrating video editing; agentic pipeline, tool-use over media primitives, natural-language-to-edit.

## License

recut's own code is [MIT licensed](LICENSE). The third-party models it depends on for analysis have their own, separate licenses — see the table above before any commercial use.
