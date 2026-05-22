import librosa
import numpy as np
import json
import sys
from scipy.signal import butter, sosfilt


# ── helpers ──────────────────────────────────────────────────────────────────

def bandpass(y, sr, low_hz, high_hz=None):
    nyq = sr / 2
    if high_hz is None or high_hz >= nyq:
        # highpass only
        sos = butter(4, low_hz / nyq, btype='high', output='sos')
    else:
        sos = butter(4, [low_hz / nyq, high_hz / nyq], btype='band', output='sos')
    return sosfilt(sos, y)

def nearest(t, times):
    arr = np.array(times)
    return float(arr[np.argmin(np.abs(arr - t))])

def beat_in_bar(t, downbeats, beat_interval):
    """Return 1-4: which beat of the bar t falls on, relative to downbeat grid."""
    if not downbeats:
        return None
    db = nearest(t, downbeats)
    offset = t - db
    beat_num = round(offset / beat_interval) % 4 + 1
    return int(beat_num)


# ── main ─────────────────────────────────────────────────────────────────────

def analyze(path, n_sections=6):
    print(f"Analyzing {path}...")
    y, sr = librosa.load(path)  # full track

    duration = round(float(len(y) / sr), 2)
    print(f"  Duration: {duration}s")

    # ── BPM + full beat grid ─────────────────────────────────────────────────
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    bpm = round(float(tempo.item()), 1)
    beat_interval = 60.0 / bpm
    print(f"  BPM: {bpm}  beats: {len(beat_times)}")

    # ── Key ──────────────────────────────────────────────────────────────────
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    keys = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    key = keys[chroma.mean(axis=1).argmax()]

    # ── Transient detection per frequency band ───────────────────────────────
    print("  Detecting transients per band...")

    y_kick  = bandpass(y, sr, 40,   200)
    y_snare = bandpass(y, sr, 200,  2000)
    y_hihat = bandpass(y, sr, 5000)  # highpass — hi-hat / cymbals

    def onsets(y_band, delta=0.07):
        frames = librosa.onset.onset_detect(
            y=y_band, sr=sr, units='frames',
            pre_max=3, post_max=3, pre_avg=5, post_avg=5, delta=delta, wait=2
        )
        times = librosa.frames_to_time(frames, sr=sr).tolist()
        return [round(t, 3) for t in times]

    kick_times  = onsets(y_kick,  delta=0.05)
    snare_times = onsets(y_snare, delta=0.07)
    hihat_times = onsets(y_hihat, delta=0.04)

    print(f"  Kick: {len(kick_times)}  Snare: {len(snare_times)}  Hi-hat: {len(hihat_times)}")

    # ── Downbeats from kick grid ─────────────────────────────────────────────
    # Beat-track gives a grid; kick hits tell us which are beat-1 candidates.
    # Strategy: for each beat, check if a kick lands within ±30ms.
    # Beats that have a kick are likely beat 1 or 3 (in 4/4).
    # We pick every other kick-aligned beat starting from the earliest,
    # at intervals of ~2 bars (8 beats) apart.

    kick_arr = np.array(kick_times)
    beat_arr = np.array(beat_times)

    kick_on_beat = []
    for b in beat_times:
        if len(kick_arr) and np.min(np.abs(kick_arr - b)) < 0.04:
            kick_on_beat.append(round(b, 3))

    # Downbeats: kick-on-beat events separated by ~4 beat intervals (1 bar)
    min_bar_gap = beat_interval * 3.5
    downbeats = []
    for t in kick_on_beat:
        if not downbeats or (t - downbeats[-1]) >= min_bar_gap:
            downbeats.append(round(t, 3))

    print(f"  Downbeats: {len(downbeats)}")

    # bars: group beats into bars of 4, anchored to first downbeat
    bars = []
    if downbeats:
        anchor = downbeats[0]
        bar_beats = []
        bar_id = 1
        for b in beat_times:
            bar_beats.append(round(b, 3))
            if len(bar_beats) == 4:
                bars.append({
                    "id": bar_id,
                    "start": bar_beats[0],
                    "beats": bar_beats
                })
                bar_id += 1
                bar_beats = []

    print(f"  Bars: {len(bars)}")

    # ── Sections ─────────────────────────────────────────────────────────────
    print("  Detecting sections...")
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    bound_frames = librosa.segment.agglomerative(mfcc, n_sections)
    raw_bounds = librosa.frames_to_time(bound_frames, sr=sr).tolist()

    def snap_to_kick_or_beat(t):
        """Snap t to nearest kick, falling back to nearest beat."""
        candidates = []
        if kick_times:
            candidates.append(nearest(t, kick_times))
        if beat_times:
            candidates.append(nearest(t, beat_times))
        return round(min(candidates, key=lambda c: abs(c - t)), 3)

    sections = []
    for i, raw_start in enumerate(raw_bounds):
        raw_end = raw_bounds[i + 1] if i + 1 < len(raw_bounds) else duration
        start = snap_to_kick_or_beat(raw_start) if raw_start > 0.1 else round(raw_start, 3)
        end   = snap_to_kick_or_beat(raw_end)   if raw_end < duration - 0.1 else round(raw_end, 3)

        # Nearest downbeat for the start
        db_start = round(nearest(start, downbeats), 3) if downbeats else None
        bib = beat_in_bar(start, downbeats, beat_interval) if downbeats else None

        sections.append({
            "id": i + 1,
            "start": start,
            "end": end,
            "duration": round(end - start, 3),
            "raw_start": round(raw_start, 3),
            "nearest_downbeat": db_start,
            "beat_in_bar": bib,
            "is_kick": start in kick_times or nearest(start, kick_times if kick_times else [start]) == start and abs(nearest(start, kick_times) - start) < 0.04 if kick_times else False
        })

    # ── Assemble map ─────────────────────────────────────────────────────────
    music_map = {
        "file": path,
        "duration": duration,
        "bpm": bpm,
        "beat_interval": round(beat_interval, 4),
        "key": key,
        "beats": [round(b, 3) for b in beat_times],
        "downbeats": downbeats,
        "bars": bars,
        "transients": {
            "kick":  kick_times,
            "snare": snare_times,
            "hihat": hihat_times,
        },
        "sections": sections,
    }

    return music_map


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "track.mp3"
    n_sections = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    result = analyze(path, n_sections)
    out = "music.map.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n✅ Saved to {out}")
    # Print summary only
    print(f"   BPM {result['bpm']} | Key {result['key']} | {len(result['beats'])} beats | "
          f"{len(result['downbeats'])} downbeats | {len(result['bars'])} bars | "
          f"{len(result['sections'])} sections")
    print(f"   Kick {len(result['transients']['kick'])} | "
          f"Snare {len(result['transients']['snare'])} | "
          f"Hi-hat {len(result['transients']['hihat'])}")
