---
title: H1-ZERO Chord Detection
emoji: 🎸
colorFrom: purple
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# H1-ZERO Chord Detection API

Full 13-step ML pipeline for music chord detection:

1. Audio loading + environment detection
2. Source separation (Demucs htdemucs_ft)
3. Genre classification (CLAP)
4. Beat/tempo detection (BeatNet + librosa)
5. Tonal features + key detection (Essentia + MERT)
6. Chord recognition (BTC + chroma)
7. Phase coherence at beat boundaries
8. Roman numeral function analysis
9. Theory smoothing (genre-adaptive Viterbi)
10. AMT on harmonic stem (Basic Pitch)
11. Drum MIDI from drum stem
12. MIDI assembly with chord markers

## API Endpoints

- `GET /` — Status check
- `GET /health` — Model availability
- `POST /analyze` — Upload audio file for chord detection

## Usage

```bash
curl -X POST https://Izreals-h1zero-chord-detection.hf.space/analyze \
  -F "file=@song.mp3"
```
