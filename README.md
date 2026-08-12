> **⚠ Early prototype / MVP** — work in progress, APIs will change.

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
modal token new   # one-time authentication, saves to ~/.modal.toml
modal deploy src/analysis/pipeline.py
```

See `src/analysis/README.md` for full analysis pipeline details.

## CLI

```bash
# Analyze an audio file → raw JSON
recut analyze path/to/track.mp3

# Build music map from raw analysis output
recut map path/to/track.mp3 temp/analysis/raw/track-raw.json

# Help
recut --help
recut analyze --help
```

Output is saved to `temp/analysis/`:
- `temp/analysis/raw/<stem>-raw.json` — raw model output
- `temp/analysis/maps/<stem>-map.json` — enriched music map

## Code Examples

_Coming soon — compositor API (clips, loops, effects, fades)._
