> **⚠ Early prototype / MVP** — work in progress, APIs may change.

# recut

Declarative audio editing — describe music edits in code, recut renders them. Inspired by [Remotion](https://www.remotion.dev), but for audio.

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

**3. Set up Modal (for audio analysis)**

Requires a [Modal account](https://modal.com) — free tier is sufficient.

```bash
pip install modal
modal token new       # one-time authentication, saves to ~/.modal.toml
modal deploy src/analysis/pipeline.py
```

Models are cloned automatically at deploy time — no manual download needed.

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

Everything recut generates lives in `.appdata/` (git-ignored):
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
import soundfile as sf
from recut.audio import Audio
from recut.map.parser import parse_recut_map
from recut.compositor import Clip, compose
from recut.compositor.effects import Fade

# Load music map and audio
music_map = parse_recut_map(".appdata/maps/enriched/summer-party.json")
audio = Audio.load(".appdata/audio/summer-party.mp3")

# Build the edit: chorus (hook) → intro → verse → inst, fading out over the last bars
result = compose(
    music_map,
    audio,
    Clip("chorus"),
    Clip("intro"),
    Clip("verse"),
    Clip("inst", bars=7),
    Clip("inst", offset_bars=7, fx=[Fade(vol_start=1.0, vol_end=0.0, curve="qsin")]),
)

sf.write("summer-party-cut.mp3", result.samples.T, result.sr)
```

`Clip.fx` takes typed `Effect` objects (`Fade`, `Reverb`, `Delay`, `FilterSweep`,
`ReverbSweep` — `recut.compositor.effects`), not the bare curried primitives
(`recut.primitives.fade.fade` etc.) — those are the lower-level building blocks
`Effect.to_fn()` wraps, not what `Clip.fx` expects directly.

**Validation** — a linter for music cuts. Before rendering, validates that all nodes are musically coherent: segment labels exist in the map, requested bars/beats don't exceed the segment duration, and the cut doesn't start or end abruptly mid-song. The goal is to grow this into a richer rule set that catches musical issues automatically — wrong key transitions, energy drops, rhythmic misalignments — so the system can eventually guide or automate cut decisions.

```python
from recut.validator import validate

issues = validate(music_map, Clip("intro"), Clip("verse"), Clip("chorus", loop=2))
# issues: list of ValidationResult with severity ("error" | "warning") and message
```

The analysis extracts tempo, time signature, song structure, beats, chords, and loudness — everything needed to make musically aware cuts.

## Agent / Harness Usage

recut ships two [Agent Skills](https://code.claude.com/docs/en/skills) at `skills/cutting/` and `skills/music-theory/` — `cutting` covers the `Clip`/`XFade`/`compose()`/`validate()` mechanics, `music-theory` covers the musical judgment behind a cut (cadence quality, hook selection, energy arcs). Point your harness at both; currently tested with Claude Code.

## Current Limitations

recut is an early prototype. A few headline gaps — full list in [`LIMITATIONS.md`](LIMITATIONS.md):

- No partial-clip effect application — an effect always applies to a clip's whole buffer, not just part of it.
- No live per-instrument/stem editing — `compose()` works on the full mix only.
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

> **⚠ MuQ is non-commercial only** (CC BY-NC 4.0, Tencent AI Lab). SongFormer uses MuQ as its audio encoder, making the structure pipeline non-commercial. Replace MuQ with a MIT-licensed alternative (MERT, EnCodec) before any commercial use.
