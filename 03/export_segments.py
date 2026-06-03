"""Export each segment from billie_jean-map.json as a separate MP3."""
import json
import soundfile as sf
import numpy as np
import librosa
from pathlib import Path

MAP = Path(__file__).parent / "billie_jean-map.json"
AUDIO = Path(__file__).parent / "billie_jean.mp3"
OUT = Path(__file__).parent / "segments"
OUT.mkdir(exist_ok=True)

with open(MAP) as f:
    music_map = json.load(f)

audio, sr = librosa.load(AUDIO, sr=None, mono=False)
# librosa loads mono as (samples,), stereo as (channels, samples)
if audio.ndim == 1:
    audio = audio[np.newaxis, :]  # (1, samples)

for seg in music_map["segments"]:
    idx = seg["index"]
    label = seg["label"]
    start_sample = int(seg["start"] * sr)
    end_sample = int(seg["end"] * sr)

    chunk = audio[:, start_sample:end_sample]  # (channels, samples)
    chunk_t = chunk.T  # soundfile wants (samples, channels)

    out_path = OUT / f"{idx:02d}-{label}.wav"
    sf.write(str(out_path), chunk_t, sr)
    print(f"  {out_path.name}  ({seg['duration']:.1f}s)")

print(f"\nExported {len(music_map['segments'])} segments to {OUT}")
