"""
xfade_join(a, b, xfade_ms, sr) → np.ndarray

Equal-power crossfade between two audio segments.
The tail of `a` fades out while the head of `b` fades in.
Place cut points in the decay zone after a downbeat for clean joins.
"""

import numpy as np


def xfade_join(a: np.ndarray, b: np.ndarray, xfade_ms: int, sr: int) -> np.ndarray:
    """
    a, b: (channels, samples) — must have at least xfade_ms worth of samples.
    Returns joined array with equal-power crossfade at the junction.
    """
    n = int(xfade_ms / 1000 * sr)
    ramp_out = np.sqrt(np.linspace(1.0, 0.0, n))
    ramp_in  = np.sqrt(np.linspace(0.0, 1.0, n))

    out = a.copy()
    out[:, -n:] *= ramp_out[np.newaxis, :]
    out[:, -n:] += b[:, :n] * ramp_in[np.newaxis, :]
    return np.concatenate([out, b[:, n:]], axis=1)
