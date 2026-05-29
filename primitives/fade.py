"""
fade(audio, sr, vol_start, vol_end) → np.ndarray

Linear volume envelope over the full audio segment.

vol_start : volume at t=0  (0.0 = silence, 1.0 = full)
vol_end   : volume at t=end (0.0 = silence, 1.0 = full)

Examples
--------
fade(audio, sr, 0.0, 1.0)  — fade in  from silence to full
fade(audio, sr, 1.0, 0.0)  — fade out from full to silence
fade(audio, sr, 0.2, 1.0)  — start quiet, ramp to full
"""

import numpy as np


def fade(
    audio: np.ndarray,
    sr: int = None,
    vol_start: float = 0.0,
    vol_end: float = 1.0,
) -> np.ndarray:
    n = audio.shape[-1]
    envelope = np.linspace(vol_start, vol_end, n)
    if audio.ndim == 2:
        envelope = envelope[np.newaxis, :]
    return audio * envelope
