"""
cut(audio, sr, start, end) → np.ndarray

Slice audio to [start, end] seconds. Hard cut, no fades.
"""

import numpy as np


def cut(audio: np.ndarray, sr: int, start: float, end: float) -> np.ndarray:
    """
    audio: (channels, samples) or (samples,)
    Returns same shape, trimmed to [start, end].
    """
    s = int(round(start * sr))
    e = int(round(end * sr))
    if audio.ndim == 1:
        return audio[s:e]
    return audio[:, s:e]
