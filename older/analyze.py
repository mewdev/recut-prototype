"""
JSONMusicMap analyzer
Uses madmom (RNN downbeat tracking) + librosa (beats, sections, transients).
Run with: /path/to/recut39/bin/python analyze.py <audio.mp3> [n_sections]
"""

# ── numpy patch for madmom compatibility ─────────────────────────────────────
import numpy as np
np.float   = np.float64
np.complex = np.complex128
np.int     = np.int64
np.bool    = np.bool_
np.object  = np.object_
np.str     = np.str_

import librosa
import json
import sys
from scipy.signal import butter, sosfilt


# ── helpers ──────────────────────────────────────────────────────────────────

def bandpass(y, sr, low_hz, high_hz=None):
    nyq = sr / 2
    if high_hz is None or high_hz >= nyq:
        sos = butter(4, low_hz / nyq, btype='high', output='sos')
    else:
        sos = butter(4, [low_hz / nyq, high_hz / nyq], btype='band', output='sos')
    return sosfilt(sos, y)

def nearest(t, arr):
    a = np.array(arr)
    return float(a[np.argmin(np.abs(a - t))])

def snap_to_grid(t, grid, tol=None):
    """Snap t to nearest value in grid."""
    return nearest(t, grid)

def infer_label(section_times, rms_series, contrast_series, sr, hop):
    """
    Energy + spectral contrast heuristic for section labeling.
    Returns label string: intro / verse / chorus / bridge / outro
    """
    labels = []
    n = len(section_times)
    energies = []
    contrasts = []

    for i, (start, end) in enumerate(section_times):
        s = int(start * sr / hop)
        e = int(end   * sr / hop)
        seg_rms  = float(np.mean(rms_series[s:e]))   if e > s else 0.0
        seg_cont = float(np.mean(contrast_series[s:e])) if e > s else 0.0
        energies.append(seg_rms)
        contrasts.append(seg_cont)

    if not energies:
        return ["unknown"] * n

    med_e = np.median(energies)
    med_c = np.median(contrasts)

    for i in range(n):
        e = energies[i]
        c = contrasts[i]
        if i == 0:
            label = "intro"
        elif i == n - 1:
            label = "outro"
        elif e > med_e * 1.1 and c > med_c:
            label = "chorus"
        elif e < med_e * 0.85:
            label = "bridge"
        else:
            label = "verse"
        labels.append(label)

    return labels


# ── main ─────────────────────────────────────────────────────────────────────

def analyze(path, n_sections=6):
    print(f"Analyzing {path}...")
    y, sr = librosa.load(path)
    duration = round(float(len(y) / sr), 2)
    hop = 512
    print(f"  Duration: {duration}s  sr: {sr}")

    # ── Beats via madmom RNN ─────────────────────────────────────────────────
    print("  Running madmom beat tracker...")
    from madmom.features.beats import RNNBeatProcessor, BeatTrackingProcessor
    beat_act   = RNNBeatProcessor()(path)
    beat_times = [round(float(t), 3) for t in BeatTrackingProcessor(fps=100)(beat_act)]

    # BPM from median beat interval
    if len(beat_times) > 1:
        intervals = np.diff(beat_times)
        bpm = round(60.0 / float(np.median(intervals)), 1)
    else:
        bpm = 0.0
    beat_interval = round(60.0 / bpm, 4) if bpm else 0.0

    # Beat positions in bar (1–4) — grouped every 4 beats from first beat
    beat_pos = [(i % 4) + 1 for i in range(len(beat_times))]

    # Downbeats = every 4th beat starting from index 0
    downbeats = [beat_times[i] for i in range(0, len(beat_times), 4)]

    print(f"  BPM: {bpm}  beats: {len(beat_times)}  downbeats: {len(downbeats)}")

    # ── Key ──────────────────────────────────────────────────────────────────
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    keys   = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    key    = keys[chroma.mean(axis=1).argmax()]

    # ── Bars ─────────────────────────────────────────────────────────────────
    bars = []
    bar_id = 1
    bar_beat_buf = []
    for t, pos in zip(beat_times, beat_pos):
        bar_beat_buf.append(round(t, 3))
        if pos == 4 or (pos == 3 and bar_id > 1):  # handle 3/4 too
            bars.append({"id": bar_id, "start": bar_beat_buf[0], "beats": bar_beat_buf})
            bar_id += 1
            bar_beat_buf = []
    print(f"  Bars: {len(bars)}")

    # ── Transients per band ──────────────────────────────────────────────────
    print("  Detecting transients...")
    y_kick  = bandpass(y, sr, 40,  200)
    y_snare = bandpass(y, sr, 200, 2000)
    y_hihat = bandpass(y, sr, 5000)

    def onsets(y_band, delta=0.07):
        frames = librosa.onset.onset_detect(
            y=y_band, sr=sr, hop_length=hop, units='frames',
            pre_max=3, post_max=3, pre_avg=5, post_avg=5, delta=delta, wait=4
        )
        return [round(float(t), 3) for t in librosa.frames_to_time(frames, sr=sr, hop_length=hop)]

    kick_times  = onsets(y_kick,  delta=0.08)
    snare_times = onsets(y_snare, delta=0.09)
    hihat_times = onsets(y_hihat, delta=0.05)
    print(f"  Kick: {len(kick_times)}  Snare: {len(snare_times)}  Hi-hat: {len(hihat_times)}")

    # ── Section boundaries ───────────────────────────────────────────────────
    print("  Detecting sections...")
    mfcc        = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop)
    bound_frames = librosa.segment.agglomerative(mfcc, n_sections)
    raw_bounds  = librosa.frames_to_time(bound_frames, sr=sr, hop_length=hop).tolist()

    # Snap each boundary to nearest downbeat
    def snap_to_downbeat(t):
        if not downbeats:
            return round(t, 3)
        return nearest(t, downbeats)

    snapped = []
    for i, t in enumerate(raw_bounds):
        s = snap_to_downbeat(t) if t > 0.5 else round(t, 3)
        snapped.append(s)

    # ── Section energy / label features ─────────────────────────────────────
    rms      = librosa.feature.rms(y=y, hop_length=hop)[0]
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr, hop_length=hop).mean(axis=0)

    section_spans = []
    for i, start in enumerate(snapped):
        end = snapped[i + 1] if i + 1 < len(snapped) else duration
        section_spans.append((start, end))

    labels = infer_label(section_spans, rms, contrast, sr, hop)

    # ── Build sections list ──────────────────────────────────────────────────
    sections = []
    for i, (start, end) in enumerate(section_spans):
        # Phrase boundaries = downbeats within this section
        phrase_boundaries = [d for d in downbeats if start <= d <= end]

        # Beat in bar at section start
        try:
            idx = beat_times.index(snap_to_downbeat(start))
            bib = beat_pos[idx]
        except (ValueError, IndexError):
            bib = None

        sections.append({
            "id": i + 1,
            "label": labels[i],
            "start": start,
            "end": end,
            "duration": round(end - start, 3),
            "duration_bars": len([d for d in downbeats if start <= d < end]),
            "raw_start": round(raw_bounds[i], 3),
            "beat_in_bar": bib,
            "phrase_boundaries": phrase_boundaries,
        })

    # ── Assemble ─────────────────────────────────────────────────────────────
    music_map = {
        "file": path,
        "duration": duration,
        "bpm": bpm,
        "beat_interval": beat_interval,
        "key": key,
        "beats": beat_times,
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
    path       = sys.argv[1] if len(sys.argv) > 1 else "track.mp3"
    n_sections = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    result     = analyze(path, n_sections)
    out        = "music.map.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n✅ Saved to {out}")
    print(f"   BPM {result['bpm']} | Key {result['key']} | "
          f"{len(result['beats'])} beats | {len(result['downbeats'])} downbeats | "
          f"{len(result['bars'])} bars | {len(result['sections'])} sections")
    for s in result['sections']:
        print(f"   §{s['id']} [{s['label']:7}] {s['start']}s → {s['end']}s "
              f"({s['duration_bars']} bars)  beat_in_bar={s['beat_in_bar']}")
