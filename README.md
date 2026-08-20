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
# Analyze an audio file → raw JSON
recut analyze path/to/track.mp3

# Build music map from raw analysis output
recut map path/to/track.mp3 .appdata/maps/raw/track-raw.json

# Help
recut --help
recut analyze --help
```

Output is saved to `.appdata/maps/`:
- `.appdata/maps/raw/<stem>-raw.json` — raw model output (beats, chords, structure)
- `.appdata/maps/enriched/<stem>-map.json` — enriched music map

## Code Example

Given an analyzed track, build a cut in code:

```python
import soundfile as sf
from recut.audio import Audio
from recut.map.parser import parse_recut_map
from recut.compositor import Clip, compose
from recut.primitives.fade import fade

# Load music map and audio
music_map = parse_recut_map(".appdata/maps/enriched/midnight_run-map.json")
audio = Audio.load("midnight_run.mp3")

# Build the edit: intro → verse → chorus × 2 (with fade out)
result = compose(
    music_map,
    audio,
    Clip("intro", snap_to_downbeat=True),
    Clip("verse"),
    Clip("chorus", loop=2, fx=[fade(vol_start=1.0, vol_end=0.0)]),
)

sf.write("midnight_run-cut.mp3", result.samples.T, result.sr)
```

**Validation** — a linter for music cuts. Before rendering, validates that all nodes are musically coherent: segment labels exist in the map, requested bars/beats don't exceed the segment duration, and the cut doesn't start or end abruptly mid-song. The goal is to grow this into a richer rule set that catches musical issues automatically — wrong key transitions, energy drops, rhythmic misalignments — so the system can eventually guide or automate cut decisions.

```python
from recut.validator import validate

issues = validate(music_map, Clip("intro"), Clip("verse"), Clip("chorus", loop=2))
# issues: list of ValidationResult with severity ("error" | "warning") and message
```

The analysis extracts tempo, time signature, song structure, beats, chords, and loudness — everything needed to make musically aware cuts.

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
