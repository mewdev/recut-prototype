from typing import Literal

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

from audio import Audio

FilterType = Literal["low", "high"]


def filter_sweep(
    filter_type: FilterType = "low",
    freq_start: float = 200.0,  # Hz — cutoff at t=0
    freq_end: float = 20000.0,  # Hz — cutoff at t=end
    duration: float | None = None,  # seconds (None = full audio length)
    curve: float = 1.0,  # sweep shape: 1.0=linear, >1=stays at start longer, <1=moves fast then slows
):
    def apply(audio: Audio) -> Audio:
        n = int((duration or audio.num_samples / audio.sr) * audio.sr)
        n_steps = 1024
        step = n // n_steps
        nyq = audio.sr / 2.0

        out = np.zeros_like(audio.samples[:, :n])

        n_channels = audio.samples.shape[0]

        sos = butter(2, freq_start / nyq, btype=filter_type, output="sos")

        zi = [sosfilt_zi(sos) * audio.samples[ch, 0] for ch in range(n_channels)]

        for i in range(n_steps):
            t = (i / (n_steps - 1)) ** curve
            freq = freq_start * (freq_end / freq_start) ** t
            sos = butter(2, freq / nyq, btype=filter_type, output="sos")
            s = i * step
            e = s + step if i < n_steps - 1 else n

            for ch in range(n_channels):
                out[ch, s:e], zi[ch] = sosfilt(sos, audio.samples[ch, s:e], zi=zi[ch])

        return Audio(out, audio.sr)

    return apply
