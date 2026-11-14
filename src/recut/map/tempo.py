"""
tempo.py — derive the tempo from a beat grid (pure functions, stdlib only)

The tempo estimator (madmom TempoEstimationProcessor) can lock onto half- or double-time
(73 bpm for a 146 bpm track). The beat grid is what the cuts actually land on, so the
map's `bpm` is derived from it: 60 / median inter-beat interval (the median ignores a few
missed or doubled beats). `src/analysis/pipeline.py` carries a verbatim copy of
`bpm_from_beats` (Modal ships only that file); tests/map/test_tempo.py keeps them equal.
"""

from statistics import median

BPM_DISAGREE_TOLERANCE = 0.05  # warn / correct when estimate and grid differ by more than 5 %
MIN_BEATS_FOR_GRID_BPM = 4


def bpm_from_beats(beats: list[float]) -> float | None:
    """60 / median inter-beat interval, or None when the grid is too short to trust."""
    if len(beats) < MIN_BEATS_FOR_GRID_BPM:
        return None
    intervals = [b - a for a, b in zip(beats, beats[1:]) if b > a]
    if not intervals:
        return None
    return 60.0 / median(intervals)


def bpm_disagrees(bpm: float, grid_bpm: float, tolerance: float = BPM_DISAGREE_TOLERANCE) -> bool:
    return abs(bpm - grid_bpm) / grid_bpm > tolerance
