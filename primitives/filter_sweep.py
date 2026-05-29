"""
filter_sweep(audio, sr, ...) → np.ndarray

DJ-style low-pass filter sweep with configurable direction, duration,
development curve, and volume envelope.

Key parameters
--------------
direction   : "open"  — low → high (muffled intro builds to full)
              "close" — high → low (full sound closes down to muffled)
duration    : length of sweep in seconds
freq_floor  : lowest cutoff (Hz) — how muffled the closed end is
freq_ceil   : highest cutoff (Hz) — how open the open end is
curve       : shape of the sweep over time
                1.0 — even octave pacing (standard log sweep)
                >1   — stays closed longer, bursts open late  (e.g. 6 = hold then burst)
                <1   — opens fast then slows (e.g. 0.3 = quick open)
vol_start   : volume at t=0  (0.0 = silence, 1.0 = full)
vol_end     : volume at t=end (0.0 = silence, 1.0 = full)
"""

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi


def filter_sweep(
    audio: np.ndarray,
    sr: int,
    direction: str = "open",     # "open" or "close"
    duration: float = 6.0,
    freq_floor: float = 220.0,   # Hz — closed/muffled end
    freq_ceil: float = 20000.0,  # Hz — open/full end
    curve: float = 1.0,
) -> np.ndarray:
    n = int(round(duration * sr))
    seg = audio[:, :n] if audio.ndim == 2 else audio[np.newaxis, :n]
    n_ch = seg.shape[0]
    nyq = sr / 2.0

    if direction == "open":
        freq_a, freq_b = freq_floor, freq_ceil
    else:  # close
        freq_a, freq_b = freq_ceil, freq_floor

    n_steps = 1024
    step = n // n_steps
    out = np.zeros_like(seg)

    f0 = min(freq_a, nyq * 0.98)
    sos = butter(2, f0 / nyq, btype="low", output="sos")
    zi = np.stack([sosfilt_zi(sos) * seg[ch, 0] for ch in range(n_ch)])

    for i in range(n_steps):
        t = (i / max(n_steps - 1, 1)) ** curve
        freq = min(freq_a * (freq_b / freq_a) ** t, nyq * 0.98)
        sos = butter(2, freq / nyq, btype="low", output="sos")

        s = i * step
        e = s + step if i < n_steps - 1 else n

        for ch in range(n_ch):
            filtered, zi[ch] = sosfilt(sos, seg[ch, s:e], zi=zi[ch])
            out[ch, s:e] = filtered

    if audio.ndim == 1:
        return out[0]
    return out
