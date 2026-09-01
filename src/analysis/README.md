# Analysis Pipeline

Two-step process: raw analysis via Modal GPU → enriched music map.

```
mp3 → [analyze] → temp/analysis/raw/<stem>-raw.json
                → [make_map]  → temp/analysis/maps/<stem>-map.json
```

The raw JSON is a direct dump from the models. The map is the enriched, LLM-ready output used by the compositor.

## Raw output (`-raw.json`)

```json
{
  "bpm": 117.5,
  "time_signature": "4/4",
  "beats": [0.51, 1.02, "..."],
  "downbeats": [0.51, 2.55, "..."],
  "segments": [{"start": 0.0, "end": 12.5, "label": "intro"}, "..."],
  "chords": [{"start": 0.0, "end": 2.3, "chord": "F#:min"}, "..."],
  "_sources": { "beats": "madmom", "chords": "chord-cnn-lstm", "structure": "songformer" }
}
```

## Models

| Step | Model | Source |
|------|-------|--------|
| Beats | madmom (RNN + DBN) | installed from GitHub at image build |
| Chords | Chord-CNN-LSTM ensemble | `models/chord-cnn-lstm/` — bundled locally |
| Structure | SongFormer (MuQ + MusicFM) | `models/songformer/` — code bundled locally, weights downloaded from HuggingFace at image build |

The `models/` directory must be present locally — Modal reads it at deploy time to bundle into the container image. See `models/README.md` for details.

## Setup

**1. Install Modal**
```bash
pip install modal
```

**2. Authenticate (one-time)**
```bash
modal token new
```
Credentials are saved to `~/.modal.toml`. See https://modal.com/docs/guide#getting-started.

**3. Deploy**
```bash
modal deploy src/analysis/pipeline.py
```
This builds three container images (beats, chords, structure) and deploys the app. Model weights that aren't bundled locally are downloaded from HuggingFace automatically during image build — this only happens once, results are cached by Modal.

## Running

```bash
# Step 1 — raw analysis (Modal GPU)
recut analyze path/to/track.mp3
# → temp/analysis/raw/<stem>-raw.json

# Step 2 — build music map (local)
recut map path/to/track.mp3
# → temp/analysis/maps/<stem>-map.json

# or directly via Modal (skips CLI)
modal run src/analysis/pipeline.py --path path/to/track.mp3
```
