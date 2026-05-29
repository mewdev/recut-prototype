"""
chain(audio, sr, *steps) → np.ndarray

Apply a sequence of audio effects in order. Each step describes one primitive call.

Usage
-----
result = chain(audio, sr,
    (filter_sweep, dict(direction="open", duration=6.0)),
    (fade,         dict(vol_start=0.0, vol_end=1.0)),
    (reverb,       dict(wetness=0.5, reverb_type="hall")),
)
"""

import numpy as np


def chain(audio: np.ndarray, sr: int, *steps) -> np.ndarray:
    for fn, kwargs in steps:
        audio = fn(audio, sr, **kwargs)
    return audio
