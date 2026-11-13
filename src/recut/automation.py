"""Automation curves for plan.json (PLAN §3.2): ramps and breakpoints → per-sample arrays.

Level targets (`gain`, `sends.<id>`; values in dB, "-inf" allowed) are interpolated in the
*linear gain* domain, so `-inf → 0` with shape `exp` is a proper swell from silence.
Frequency parameters are interpolated geometrically (log-frequency), everything else
linearly. The ramp shape (linear/equal_power/exp/log/hold) warps the 0→1 progress.

Several automations on one target are applied in order: the first one holds its first value
before it starts and its last value after it ends; later ones only overwrite the curve from
their own start onward.
"""

from typing import Optional

import numpy as np

from recut.contracts.plan import Automation, Points, Ramp
from recut.contracts.units import db_to_gain, parse_time, ramp_in


class AutomationError(ValueError):
    """Bad automation entry. Message is agent-facing."""


def _value(v, kind: str) -> float:
    if kind == "level":
        return db_to_gain(v)
    if isinstance(v, str):
        raise AutomationError(f'only levels accept "-inf" (got {v!r} for a non-level target)')
    return float(v)


def _interp(a: float, b: float, w: np.ndarray, kind: str) -> np.ndarray:
    if kind == "freq" and a > 0 and b > 0:
        return np.exp(np.log(a) + (np.log(b) - np.log(a)) * w)
    return a + (b - a) * w


def _span(au: Automation, n: int, sr: int, bpm: float, bpb: int, length_s: float) -> tuple[float, float]:
    """(start, end) of the automation in seconds relative to its owner's start."""
    if isinstance(au, Ramp):
        over = parse_time(au.over, bpm, bpb)
        if au.at == "start":
            rel = 0.0
        elif au.at == "end":
            rel = length_s - over
        else:
            rel = parse_time(au.at, bpm, bpb)
        if rel < -1e-9:
            raise AutomationError(
                f"automation on {au.target}: ramp over {au.over} is longer than the clip ({length_s:.2f}s)")
        return max(rel, 0.0), max(rel, 0.0) + over
    times = [parse_time(t, bpm, bpb) for t, _ in au.points]
    return times[0], times[-1]


def spans(autos: list[Automation], target: str, sr: int, bpm: float, bpb: int, length_s: float):
    return [(au, *_span(au, 0, sr, bpm, bpb, length_s)) for au in autos if au.target == target]


def build_curve(autos: list[Automation], target: str, n: int, sr: int, bpm: float, bpb: int,
                kind: str = "linear", length_s: Optional[float] = None) -> Optional[np.ndarray]:
    """Per-sample curve for `target` (length n), or None if nothing automates it.

    kind: "level" (dB in → linear gain out), "freq" (Hz, geometric), "linear" (raw units).
    `length_s` is the owner's length in seconds (for `at: "end"`); defaults to n / sr.
    """
    length_s = n / sr if length_s is None else length_s
    mine = [au for au in autos if au.target == target]
    if not mine:
        return None
    curve = np.zeros(n, dtype=np.float64)
    for k, au in enumerate(mine):
        t0, t1 = _span(au, n, sr, bpm, bpb, length_s)
        if isinstance(au, Ramp):
            a, b = _value(au.from_, kind), _value(au.to, kind)
            i0, i1 = int(round(t0 * sr)), int(round(t1 * sr))
            if k == 0:
                curve[: min(i0, n)] = a
            if i0 < n:
                seg = _interp(a, b, ramp_in(au.shape, max(i1 - i0, 0)), kind)[: n - i0]
                curve[i0 : i0 + len(seg)] = seg
            if i1 < n:
                curve[i1:] = b
        else:
            pts = [(parse_time(t, bpm, bpb), _value(v, kind)) for t, v in au.points]
            if any(b[0] < a[0] for a, b in zip(pts, pts[1:])):
                raise AutomationError(f"automation on {au.target}: points must be in time order")
            idx = [int(round(t * sr)) for t, _ in pts]
            if k == 0:
                curve[: min(idx[0], n)] = pts[0][1]
            for (i0, i1), (_, a), (_, b) in zip(zip(idx, idx[1:]), pts, pts[1:]):
                if i0 >= n:
                    break
                seg = _interp(a, b, ramp_in(au.shape, max(i1 - i0, 0)), kind)[: n - i0]
                curve[i0 : i0 + len(seg)] = seg
            if idx[-1] < n:
                curve[idx[-1]:] = pts[-1][1]
    return curve


def span_seconds(au: Automation, bpm: float, bpb: int, length_s: float) -> tuple[float, float]:
    """Where an automation is active, relative to its owner's start (for render.json)."""
    return _span(au, 0, 0, bpm, bpb, length_s)


__all__ = ["AutomationError", "build_curve", "span_seconds", "Points", "Ramp"]
