# H1-ZERO Chord Detection — Local Setup

Chord + key analysis API. Returns timestamped chords, Roman numerals, key, tempo, beats.

Source: https://huggingface.co/spaces/Izreals/h1zero-chord-detection

---

## Run with Docker (recommended)

```bash
cd h1zero-chord-detection

# Build (takes ~10-15 min first time — downloads CLAP model ~1.5GB)
docker build -t h1zero .

# Run
docker run -p 8000:7860 h1zero
```

Server is up at http://localhost:8000

---

## Analyze a file

```bash
# Health check
curl http://localhost:8000/health

# Analyze audio file → save results as JSON
curl -X POST http://localhost:8000/analyze \
  -F "file=@../modern-classic/Building A Family (1).mp3" \
  -o chords.json
```

Takes ~1-2 min per track on CPU.

---

## Output format

```json
{
  "key": "A",
  "scale": "major",
  "tempo": 126.0,
  "time_signature": 4,
  "chords": [
    { "time": 24.26, "chord": "E", "confidence": 0.94, "roman": "V", "function": "dominant" }
  ],
  "beats": [...],
  "downbeats": [...]
}
```

---

## Run against the hosted version (no Docker needed)

The original space is still live if you don't want to build locally:

```bash
curl -X POST https://Izreals-h1zero-chord-detection.hf.space/analyze \
  -F "file=@your_audio.mp3" \
  -o chords.json
```

---

## What's inside

| File | Role |
|---|---|
| `Dockerfile` | Installs all deps, pre-caches CLAP model |
| `api.py` | FastAPI server — `/analyze` endpoint |
| `h1_zero_pipeline.py` | 13-step pipeline: HPSS → genre (CLAP) → beats (BeatNet) → key (Essentia/chroma) → chords (BTC-style + Viterbi) → MIDI (Basic Pitch) |

No custom trained weights — uses laion/larger_clap_music, BeatNet, Basic Pitch, Essentia.
