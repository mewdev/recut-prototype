from typing import Literal

import numpy as np

from recut.audio import Audio

Curve = Literal["linear", "log", "exp", "qsin"]


def fade(vol_start: float = 0.0, vol_end: float = 1.0, curve: Curve = "linear"):
    """
    vol_start: volume at beginning, 0.0 silence, 1.0 default volume
    vol_end:   volume at end, 1.0 default volume, 0.0 silence
    curve:     shape of the fade, options: linear, log, exp, qsin
    """

    def make_envelope(vol_start, vol_end, num_samples, curve: Curve):
        match curve:
            case "linear":
                return np.linspace(vol_start, vol_end, num_samples)
            case "log":
                return np.geomspace(max(vol_start, 0.001), max(vol_end, 0.001), num_samples)
            case "exp":
                return np.linspace(0, 1, num_samples) ** 2 * (vol_end - vol_start) + vol_start
            case "qsin":
                return (
                    np.sin(np.linspace(0, np.pi / 2, num_samples)) * (vol_end - vol_start)
                    + vol_start
                )

    def apply(audio: Audio) -> Audio:

        envelope = make_envelope(vol_start, vol_end, audio.num_samples, curve)

        return audio.apply_to_channels(lambda ch: ch * envelope)

    return apply
