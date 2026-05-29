"""
eq_sweep(audio, sr, duration, freq_start, freq_end) → np.ndarray

DJ-style intro: crossfade between two filtered versions of the audio
(low-pass at freq_start → low-pass at freq_end), combined with a volume fade-in.

Approach: filter the whole segment twice, blend — avoids clicks from
filter state discontinuities that happen when restarting filters per-chunk.
"""

import numpy as np
from scipy.signal import butter, sosfilt


def eq_sweep(
    audio: np.ndarray,
    sr: int,
    duration: float = 6.0,
    freq_start: float = 300.0,
    freq_end: float = 18000.0,
) -> np.ndarray:
    n = int(round(duration * sr))
    seg = audio[:, :n] if audio.ndim == 2 else audio[:n]
    nyq = sr / 2.0

    def lpf(sig, freq):
        freq = min(freq, nyq * 0.98)
        sos = butter(4, freq / nyq, btype="low", output="sos")
        return sosfilt(sos, sig, axis=-1)

    low  = lpf(seg, freq_start)
    high = lpf(seg, freq_end)

    # blend: 0 → 1 over duration (low → high)
    blend = np.linspace(0.0, 1.0, n)
    if audio.ndim == 2:
        blend = blend[np.newaxis, :]

    result = low * (1 - blend) + high * blend

    # volume fade-in
    fade = np.linspace(0.0, 1.0, n)
    if audio.ndim == 2:
        fade = fade[np.newaxis, :]
    result *= fade

    return result
