"""
eq(audio, sr, cutoff, type, order) → np.ndarray

Static Butterworth EQ filter — low-pass, high-pass, or band-pass.

Parameters
----------
cutoff  : cutoff frequency in Hz, or [low, high] for bandpass
type    : "low" | "high" | "band"
order   : filter order (default 4)

Examples
--------
eq(drums, sr, cutoff=120,        type="high")   # remove kick low-end before reverb
eq(audio, sr, cutoff=8000,       type="low")    # remove harshness
eq(audio, sr, cutoff=[200, 3000], type="band")  # isolate midrange
"""

import numpy as np
from scipy.signal import butter, sosfilt


def eq(
    audio: np.ndarray,
    sr: int,
    cutoff: float | list = 1000.0,
    type: str = "low",
    order: int = 4,
) -> np.ndarray:
    nyq = sr / 2.0
    if type == "band":
        freq = [c / nyq for c in cutoff]
    else:
        freq = cutoff / nyq
    sos = butter(order, freq, btype=type, output="sos")
    return sosfilt(sos, audio, axis=-1)
