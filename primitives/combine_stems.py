"""
combine_stems(*stems) → np.ndarray

Sum multiple stem arrays into a single mix. All stems must have the same
shape (channels, samples). Optionally normalise to prevent clipping.

Parameters
----------
stems      : two or more np.ndarray of shape (channels, samples)
normalise  : if True, scale output so peak does not exceed 0.95
"""

import numpy as np


def combine_stems(*stems: np.ndarray, normalise: bool = False) -> np.ndarray:
    mix = sum(stems)
    if normalise:
        peak = np.max(np.abs(mix))
        if peak > 0.95:
            mix = mix * (0.95 / peak)
    return mix
