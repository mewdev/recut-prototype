"""
delay(audio, sr, delay_seconds, feedback, wetness) → np.ndarray

Echo/delay effect using Spotify's pedalboard library.

Parameters
----------
delay_seconds : delay time in seconds — set to a musical subdivision for rhythmic feel
                e.g. for 83 BPM: 1 beat=0.723s, half-beat=0.361s, quarter=0.181s
feedback      : 0.0–1.0 — how much of the output feeds back into the delay
                0.0 = single echo, 0.5 = several repeats, 0.9 = long tail
wetness       : 0.0–1.0 — mix of dry vs delayed signal
"""

import numpy as np
from pedalboard import Delay, Pedalboard


def delay(
    audio: np.ndarray,
    sr: int,
    delay_seconds: float = 0.361,
    feedback: float = 0.4,
    wetness: float = 0.4,
) -> np.ndarray:
    board = Pedalboard([
        Delay(
            delay_seconds=delay_seconds,
            feedback=feedback,
            mix=wetness,
        )
    ])

    mono = audio.ndim == 1
    sig = audio[np.newaxis, :].astype(np.float32) if mono else audio.astype(np.float32)
    out = board(sig, sr)
    return out[0] if mono else out
