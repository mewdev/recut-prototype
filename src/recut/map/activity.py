"""
activity.py — M1: instrument activity curves from separated stems (pure maths, no Modal, no GPU).

    stem_activity(samples, sr)                      -> 0-1 curve, one value per 100 ms
    activity_ranges(values, hop_s, min_len_s)       -> spans where activity stays above 0.25
    bar_seconds(...)                                -> bar length from the map's beat grid
    instrument_activity_from_curves(curves, bar_s)  -> InstrumentActivity (schema type)
    apply_activity(music_map, curves)               -> MusicMap with activity + segment means

Definition (per stem): RMS in non-overlapping 100 ms hops (the last hop may be shorter) → dBFS
(floored at -100) → 0-1 where -50 dBFS = 0 and the stem's own 95th percentile = 1, clipped →
smoothed with a 300 ms centred moving average (3 hops, edges use the hops that exist). A silent
stem is all zeros, never NaN. A stem active in under 5% of the track has its 95th percentile at
or below the floor: its peak is then the reference, unless the peak is under -30 dBFS (bleed or
silence), which gives zeros. Sample i covers
[i * hop_s, (i + 1) * hop_s).

`stem_activity` is duplicated VERBATIM in src/analysis/pipeline.py (Modal ships only that file);
tests/map/test_activity.py keeps the two equal.
"""

from pathlib import Path
from typing import Optional

import numpy as np

from recut.map.musicdata import segment_mean
from recut.map.schema import InstrumentActivity, MusicMap, StemActivity

HOP_S = 0.1
FLOOR_DB = -50.0
SMOOTH_S = 0.3
RANGE_THRESHOLD = 0.25
FALLBACK_BAR_S = 2.0  # no usable beat grid / tempo: 4 beats at 120 bpm
SOURCE = "demucs-htdemucs"
# Demucs stem name → InstrumentActivity field
STEM_FIELD = {"drums": "drum", "bass": "bass", "vocals": "vocal", "other": "other"}
STEM_NAMES = tuple(STEM_FIELD)


def stem_activity(samples, sr: int, hop_s: float = HOP_S, smooth_s: float = SMOOTH_S,
                  floor_db: float = FLOOR_DB) -> list:
    """0-1 activity curve of one stem (mono, or channels x samples: channels are averaged)."""
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim == 2:
        x = x.mean(axis=0)
    hop = max(1, int(round(hop_s * sr)))
    n = int(np.ceil(len(x) / hop))
    if n == 0:
        return []
    pad = n * hop - len(x)
    sq = np.concatenate([x * x, np.zeros(pad)]).reshape(n, hop).sum(axis=1)
    counts = np.full(n, hop, dtype=np.float64)
    if pad:
        counts[-1] = hop - pad
    db = 20 * np.log10(np.maximum(np.sqrt(sq / counts), 1e-5))
    top = float(np.percentile(db, 95))
    if top <= floor_db:  # a stem active under 5% of the time: use its peak, if it is clearly audible
        top = float(db.max())
        if top < floor_db + 20.0:  # silent, or only bleed: no activity
            return [0.0] * n
    v = np.clip((db - floor_db) / (top - floor_db), 0.0, 1.0)
    k = max(1, int(round(smooth_s / hop_s)))
    if k > 1:
        w = np.ones(k)
        v = np.convolve(v, w, mode="same") / np.convolve(np.ones(n), w, mode="same")
    return [round(float(a), 4) for a in np.clip(v, 0.0, 1.0)]


def activity_ranges(values, hop_s: float = HOP_S, min_len_s: float = FALLBACK_BAR_S,
                    threshold: float = RANGE_THRESHOLD) -> list[tuple[float, float]]:
    """[start, end] seconds of runs where activity > threshold lasting at least `min_len_s`."""
    out: list[tuple[float, float]] = []
    start: Optional[int] = None
    for i, v in enumerate(list(values) + [0.0]):  # sentinel closes a run that reaches the end
        if v > threshold and start is None:
            start = i
        elif v <= threshold and start is not None:
            a, b = start * hop_s, i * hop_s
            if b - a >= min_len_s - 1e-9:
                out.append((round(a, 3), round(b, 3)))
            start = None
    return out


def bar_seconds(bars=None, beats=None, bpm: Optional[float] = None, beats_per_bar: int = 4) -> float:
    """Bar length: median downbeat spacing, else beats_per_bar beats, else from bpm, else 2 s."""
    for grid, per in ((bars, 1), (beats, beats_per_bar)):
        if grid is not None and len(grid) >= 3:
            d = np.diff(np.asarray(grid, dtype=float))
            d = d[d > 0]
            if d.size:
                return float(np.median(d)) * per
    if bpm and bpm > 0:
        return beats_per_bar * 60.0 / bpm
    return FALLBACK_BAR_S


def instrument_activity_from_curves(curves: dict, bar_s: float, hop_s: float = HOP_S) -> InstrumentActivity:
    """`curves` maps stem name (drums/bass/vocals/other) → values. Unknown names are ignored."""
    fields = {
        STEM_FIELD[name]: StemActivity(hop_s=hop_s, values=list(vals),
                                       ranges=activity_ranges(vals, hop_s, bar_s))
        for name, vals in curves.items() if name in STEM_FIELD
    }
    return InstrumentActivity(**fields)


def apply_activity(music_map: MusicMap, curves: dict, hop_s: float = HOP_S) -> MusicMap:
    """Set instrument_activity, analysis_sources.instrument_activity and each segment's
    drum_activity / vocal_activity (means). The map's own beat grid gives the bar length."""
    bar_s = bar_seconds(music_map.bars, music_map.beats, music_map.bpm, music_map.beats_per_bar)
    ia = instrument_activity_from_curves(curves, bar_s, hop_s)
    sources = dict(music_map.analysis_sources or {})
    sources["instrument_activity"] = SOURCE

    def summary(sa: Optional[StemActivity], seg) -> Optional[float]:
        return None if sa is None else segment_mean(sa.values, sa.hop_s, seg.start, seg.end)

    segments = [s.model_copy(update={"drum_activity": summary(ia.drum, s),
                                     "vocal_activity": summary(ia.vocal, s)})
                for s in music_map.segments]
    return music_map.model_copy(update={"instrument_activity": ia, "analysis_sources": sources,
                                        "segments": segments})


def has_activity(music_map: MusicMap) -> bool:
    return music_map.instrument_activity is not None


def activity_at(music_map: MusicMap, stem: str, t: float) -> Optional[float]:
    """Activity (0-1) of `stem` ("drum"/"bass"/"vocal"/"other") at time t; None if the map has none."""
    ia = music_map.instrument_activity
    sa = getattr(ia, stem, None) if ia else None
    if sa is None or not sa.values:
        return None
    return sa.values[min(len(sa.values) - 1, max(0, int(t / sa.hop_s)))]


def curves_from_stems_dir(stems_dir: Path) -> Optional[dict]:
    """Curves from saved stems (`<stems_dir>/<stem>.flac`); None unless all four are there."""
    import soundfile as sf

    paths = {name: Path(stems_dir) / f"{name}.flac" for name in STEM_NAMES}
    if not all(p.exists() for p in paths.values()):
        return None
    out = {}
    for name, p in paths.items():
        x, sr = sf.read(p, dtype="float32", always_2d=True)
        out[name] = stem_activity(x.T, int(sr))
    return out
