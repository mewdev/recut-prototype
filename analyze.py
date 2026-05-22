import librosa
import json
import sys

def analyze(path):
    print(f"Analyzing {path}...")
    y, sr = librosa.load(path, duration=120)  # first 2 mins, faster

    # BPM + beats
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beats, sr=sr).tolist()

    # Key from chroma
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)
    keys = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    key = keys[chroma_mean.argmax()]

    # Section boundaries (no labels — 6 sections)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    bounds = librosa.segment.agglomerative(mfcc, 6)
    bound_times = librosa.frames_to_time(bounds, sr=sr).tolist()

    sections = []
    for i, start in enumerate(bound_times):
        end = bound_times[i+1] if i+1 < len(bound_times) else float(len(y)/sr)
        sections.append({
            "id": i + 1,
            "start": round(start, 2),
            "end": round(end, 2),
            "duration": round(end - start, 2)
        })

    music_map = {
        "file": path,
        "duration": round(float(len(y) / sr), 2),
        "bpm": round(float(tempo.item()), 1),
        "key": key,
        "beats": [round(b, 3) for b in beat_times[:32]],
        "sections": sections
    }

    return music_map

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "track.mp3"
    result = analyze(path)
    with open("music.map.json", "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
    print("\n✅ Saved to music.map.json")
