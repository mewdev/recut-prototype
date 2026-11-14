"""
musicdata.py — M2: pace, short-term loudness and key ranges, computed locally (CPU) from audio.

    enrich_map(music_map, audio, sr) -> MusicMap     # fills what is missing, adds segment pace

Used by `make_map.run` (new maps) and by `recut map --enrich` / `recut ticket enrich` (existing
maps: only the audio and the map's own beat grid are needed, no re-analysis).

Definitions (all series are sampled every `hop_s` = 1 s; sample i is centred on t = i * hop_s and
its window is clipped at the track edges, so a track of D seconds has floor(D) + 1 samples):
- pace: librosa onset detection on the full mix; events/min in 4 s windows. `normalized` divides by
  the track's own 95th percentile and clips to 0-1 (0 = no onsets, 1 = as busy as the track gets).
- loudness_short_term: EBU R128 short-term loudness (K-weighted, 3 s window, ungated), LUFS,
  floored at -70 (digital silence), never -inf.
- key_ranges: non-overlapping 8-bar windows starting at the first downbeat, a key per window,
  equal neighbours merged. A window is a full 8 bars, so a reported change always lasts >= 8
  bars; a trailing remainder shorter than 8 bars joins the last window. The first range starts at
  0.0 and the last ends at the track's end. Key source: Essentia when `key_essentia.available()`
  (it crashes on Intel Macs, see qc_essentia), else librosa chroma + Krumhansl-Schmuckler profiles
  (`analysis_sources.key_ranges` says which one ran). The chroma fallback is less accurate on
  modal / ambiguous music; it also confuses relative major/minor more often.
"""

import numpy as np

from recut import key_essentia
from recut.map.schema import KeyRange, LoudnessShortTerm, MusicMap, Pace

HOP_S = 1.0
PACE_WINDOW_S = 4.0
LOUDNESS_WINDOW_S = 3.0
LUFS_FLOOR = -70.0
KEY_WINDOW_BARS = 8
SRC_PACE = "librosa-onsets"
SRC_LOUDNESS = "ebu-r128-short-term"
SRC_KEY_ESSENTIA = "essentia-key-8bar"
SRC_KEY_CHROMA = "librosa-chroma-krumhansl-8bar"

# Krumhansl-Kessler key profiles, tonic first
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _n_samples(duration: float, hop_s: float = HOP_S) -> int:
    return int(duration // hop_s) + 1


def _centres(duration: float, hop_s: float = HOP_S) -> np.ndarray:
    return np.arange(_n_samples(duration, hop_s)) * hop_s


# ---- pace ---------------------------------------------------------------------------------


def compute_pace(audio: np.ndarray, sr: int) -> Pace:
    import librosa

    duration = len(audio) / sr
    onsets = np.asarray(librosa.onset.onset_detect(y=audio, sr=sr, units="time"), dtype=float)
    t = _centres(duration)
    lo = np.clip(t - PACE_WINDOW_S / 2, 0.0, None)
    hi = np.minimum(t + PACE_WINDOW_S / 2, duration)
    counts = np.searchsorted(onsets, hi, side="left") - np.searchsorted(onsets, lo, side="left")
    epm = counts / np.maximum(hi - lo, 1e-6) * 60.0
    ref = float(np.percentile(epm, 95)) if epm.size else 0.0
    norm = np.clip(epm / ref, 0.0, 1.0) if ref > 0 else np.zeros_like(epm)
    return Pace(hop_s=HOP_S, events_per_min=[round(float(v), 2) for v in epm],
                normalized=[round(float(v), 4) for v in norm])


# ---- short-term loudness ------------------------------------------------------------------


def compute_loudness_short_term(audio: np.ndarray, sr: int) -> LoudnessShortTerm:
    import pyloudnorm as pyln
    from scipy import signal

    duration = len(audio) / sr
    sos = np.vstack([signal.tf2sos(f.b, f.a) for f in pyln.Meter(sr)._filters.values()])
    z = signal.sosfilt(sos, np.asarray(audio, dtype=np.float64)) ** 2
    csum = np.concatenate([[0.0], np.cumsum(z)])
    t = _centres(duration)
    lo = (np.clip(t - LOUDNESS_WINDOW_S / 2, 0.0, None) * sr).astype(int)
    hi = (np.minimum(t + LOUDNESS_WINDOW_S / 2, duration) * sr).astype(int)
    hi = np.maximum(hi, lo + 1)
    hi = np.minimum(hi, len(z))
    lo = np.minimum(lo, np.maximum(hi - 1, 0))
    ms = (csum[hi] - csum[lo]) / np.maximum(hi - lo, 1)
    lufs = np.maximum(-0.691 + 10 * np.log10(np.maximum(ms, 1e-12)), LUFS_FLOOR)
    return LoudnessShortTerm(hop_s=HOP_S, lufs=[round(float(v), 2) for v in lufs])


# ---- key ranges ---------------------------------------------------------------------------


def _chroma_key(window: np.ndarray, sr: int) -> tuple[str, str]:
    import librosa

    chroma = librosa.feature.chroma_stft(y=window, sr=sr, n_fft=4096, hop_length=2048).mean(axis=1)
    best, best_r = ("C", "major"), -2.0
    for mode, prof in (("major", _MAJOR), ("minor", _MINOR)):
        for k in range(12):
            r = float(np.corrcoef(chroma, np.roll(prof, k))[0, 1])
            if r > best_r:
                best, best_r = (_NAMES[k], mode), r
    return best


def _window_key(window: np.ndarray, sr: int, use_essentia: bool) -> tuple[str, str] | None:
    if window.size < sr or float(np.sqrt(np.mean(window**2))) < 1e-4:  # too short / silent
        return None
    if use_essentia:
        tonic, mode, _ = key_essentia.estimate_key(window, sr)
        return tonic, mode
    return _chroma_key(window, sr)


def compute_key_ranges(audio: np.ndarray, sr: int, downbeats: list[float],
                       use_essentia: bool | None = None) -> tuple[list[KeyRange], str]:
    """(ranges, analysis source). `use_essentia=None` picks Essentia when it is available."""
    if use_essentia is None:
        use_essentia = key_essentia.available()
    duration = len(audio) / sr
    bounds = list(downbeats[::KEY_WINDOW_BARS])
    n_full = len(downbeats) // KEY_WINDOW_BARS
    if n_full >= 1:  # full windows only: a trailing remainder joins the last one
        edges = bounds[:n_full] + [duration]
        edges[0] = 0.0  # the lead-in before the first downbeat belongs to the first window
    else:
        edges = [0.0, duration]
    keys = []
    for a, b in zip(edges, edges[1:]):
        keys.append(_window_key(audio[int(a * sr): int(b * sr)], sr, use_essentia))
    # silent windows inherit a neighbour's key
    known = [k for k in keys if k]
    if not known:
        return [], SRC_KEY_ESSENTIA if use_essentia else SRC_KEY_CHROMA
    prev = known[0]
    for i, k in enumerate(keys):
        keys[i] = k or prev
        prev = keys[i]
    ranges: list[KeyRange] = []
    for (a, b), k in zip(zip(edges, edges[1:]), keys):
        if ranges and (ranges[-1].tonic, ranges[-1].mode) == k:
            ranges[-1] = ranges[-1].model_copy(update={"end": b})
        else:
            ranges.append(KeyRange(start=a, end=b, tonic=k[0], mode=k[1]))
    return ranges, SRC_KEY_ESSENTIA if use_essentia else SRC_KEY_CHROMA


# ---- map enrichment -----------------------------------------------------------------------


def segment_mean(series: list[float], hop_s: float, start: float, end: float) -> float:
    """Mean of the samples centred inside [start, end) (nearest sample for a very short span)."""
    if not series:
        return 0.0
    i0, i1 = int(np.ceil(start / hop_s)), int(np.ceil(end / hop_s))
    vals = series[i0:i1]
    if not vals:
        vals = [series[min(len(series) - 1, max(0, int(round((start + end) / 2 / hop_s))))]]
    return round(float(np.mean(vals)), 4)


def enrich_map(music_map: MusicMap, audio: np.ndarray, sr: int, force: bool = False) -> MusicMap:
    """Add pace, short-term loudness, key ranges and per-segment pace. Fields the map already
    has are kept unless `force`. instrument_activity (M1) is never touched."""
    update: dict = {}
    sources = dict(music_map.analysis_sources or {})
    pace = music_map.pace
    if pace is None or force:
        pace = compute_pace(audio, sr)
        update["pace"] = pace
        sources["pace"] = SRC_PACE
    if music_map.loudness_short_term is None or force:
        update["loudness_short_term"] = compute_loudness_short_term(audio, sr)
        sources["loudness_short_term"] = SRC_LOUDNESS
    if music_map.key_ranges is None or force:
        ranges, src = compute_key_ranges(audio, sr, music_map.bars)
        update["key_ranges"] = ranges
        sources["key_ranges"] = src
    update["analysis_sources"] = sources
    update["segments"] = [
        s.model_copy(update={"pace": segment_mean(pace.normalized, pace.hop_s, s.start, s.end)})
        for s in music_map.segments
    ]
    return music_map.model_copy(update=update)
