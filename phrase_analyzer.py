"""
phrase_analyzer.py — adds phrase-level structure to a music map JSON.

For each segment:
  1. Find the best N-bar phrase grid (4/8/16/32) that fits the segment duration
  2. Split into equal N-bar phrases using actual downbeats as snap points
  3. Compare consecutive phrase chromas to detect repetitions

Output: writes an updated JSON with a top-level "phrases" array.

Usage:
    python phrase_analyzer.py testing/02/chicago-full.json testing/02/chicago.mp3
"""

import sys
import json
import numpy as np
import librosa

# ---------------------------------------------------------------------------
# Grid fitting
# ---------------------------------------------------------------------------

def best_phrase_grid(segment_dur: float, bar_dur: float) -> int:
    """Return the phrase length in bars (4/8/16/32) that most evenly divides the segment."""
    segment_bars = round(segment_dur / bar_dur)
    if segment_bars < 4:
        return 4

    candidates = [4, 8, 16, 32]
    best, best_score = 4, float("inf")
    for c in candidates:
        if c > segment_bars:
            break
        remainder = segment_bars % c
        score = min(remainder, c - remainder)  # distance from a clean fit
        if score < best_score:
            best_score, best = score, c
    return best


# ---------------------------------------------------------------------------
# Chroma similarity
# ---------------------------------------------------------------------------

def chroma_similarity(y1: np.ndarray, y2: np.ndarray, sr: int) -> float:
    """
    Returns cosine similarity [0, 1] between the mean chroma vectors of two audio segments.
    1.0 = identical harmonic content, 0.0 = orthogonal.
    """
    def mean_chroma(y):
        c = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
        return c.mean(axis=1)  # shape (12,)

    c1 = mean_chroma(y1)
    c2 = mean_chroma(y2)
    norm = np.linalg.norm(c1) * np.linalg.norm(c2)
    if norm == 0:
        return 0.0
    return float(np.dot(c1, c2) / norm)


# ---------------------------------------------------------------------------
# Downbeat snapping
# ---------------------------------------------------------------------------

def snap_to_downbeat(t: float, downbeats: list[float], direction: str = "nearest") -> float:
    """Snap time t to the nearest (or next/prev) downbeat."""
    arr = np.array(downbeats)
    if direction == "nearest":
        idx = np.argmin(np.abs(arr - t))
    elif direction == "next":
        candidates = arr[arr >= t]
        idx = np.argmin(np.abs(candidates - t)) if len(candidates) else -1
        return float(candidates[idx]) if len(candidates) else t
    elif direction == "prev":
        candidates = arr[arr <= t]
        idx = np.argmin(np.abs(candidates - t)) if len(candidates) else 0
        return float(candidates[idx]) if len(candidates) else t
    return float(arr[idx])


# ---------------------------------------------------------------------------
# Main phrase detection
# ---------------------------------------------------------------------------

def analyze_phrases(map_path: str, audio_path: str) -> dict:
    with open(map_path) as f:
        music_map = json.load(f)

    bpm = music_map["bpm"]
    bar_dur = 4 * 60.0 / bpm  # 4/4 assumed
    downbeats = music_map["downbeats"]
    segments = music_map["segments"]

    print(f"BPM={bpm}, bar_dur={bar_dur:.3f}s")

    y, sr = librosa.load(audio_path, sr=None, mono=True)
    print(f"Loaded audio: {len(y)/sr:.1f}s @ {sr}Hz")

    phrases = []

    for seg in segments:
        label = seg["label"]
        seg_start = seg["start"]
        seg_end = seg["end"]
        seg_dur = seg_end - seg_start

        # Skip very short segments (intro/start markers)
        if seg_dur < bar_dur * 3:
            print(f"  [{label}] {seg_start:.2f}–{seg_end:.2f}s — too short, skipping")
            continue

        phrase_bars = best_phrase_grid(seg_dur, bar_dur)
        phrase_dur = phrase_bars * bar_dur

        # Build phrase boundaries by stepping phrase_dur from seg_start,
        # snapping each boundary to the nearest downbeat
        t = seg_start
        phrase_boundaries = []
        while t < seg_end - bar_dur:  # stop if less than 1 bar remains
            snapped = snap_to_downbeat(t, downbeats, "nearest")
            phrase_boundaries.append(snapped)
            t += phrase_dur

        phrase_boundaries.append(snap_to_downbeat(seg_end, downbeats, "nearest"))

        print(f"  [{label}] {seg_start:.2f}–{seg_end:.2f}s ({seg_dur:.1f}s) → {phrase_bars}-bar grid → {len(phrase_boundaries)-1} phrase(s)")

        # Extract audio + compute similarity vs previous phrase in this segment
        prev_audio = None
        first_phrase_idx = len(phrases)

        for i in range(len(phrase_boundaries) - 1):
            p_start = phrase_boundaries[i]
            p_end = phrase_boundaries[i + 1]
            p_dur = p_end - p_start

            if p_dur < 0.5:
                continue

            s0 = int(p_start * sr)
            s1 = int(p_end * sr)
            seg_audio = y[s0:s1]

            # Similarity vs previous phrase
            similarity = None
            repeat_of = None
            if prev_audio is not None and len(seg_audio) > 0 and len(prev_audio) > 0:
                similarity = chroma_similarity(seg_audio, prev_audio, sr)
                if similarity >= 0.90:
                    repeat_of = len(phrases) - 1  # index of previous phrase

            phrases.append({
                "start": round(p_start, 3),
                "end": round(p_end, 3),
                "bars": phrase_bars,
                "segment": label,
                "repeat_of": repeat_of,
                "similarity": round(similarity, 3) if similarity is not None else None,
            })

            prev_audio = seg_audio

    music_map["phrases"] = phrases
    return music_map


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: phrase_analyzer.py <map.json> <audio.mp3>")
        sys.exit(1)

    map_path = sys.argv[1]
    audio_path = sys.argv[2]

    updated = analyze_phrases(map_path, audio_path)

    out_path = map_path.replace(".json", "-phrases.json")
    with open(out_path, "w") as f:
        json.dump(updated, f, indent=2)

    print(f"\nWrote {len(updated['phrases'])} phrases → {out_path}")
    for p in updated["phrases"]:
        rep = f" ← repeat_of={p['repeat_of']} (sim={p['similarity']})" if p["repeat_of"] is not None else ""
        print(f"  {p['segment']:12s} {p['start']:6.2f}–{p['end']:6.2f}s  {p['bars']}-bar{rep}")
