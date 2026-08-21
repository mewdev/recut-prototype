"""Shared volume envelope curves used by fade, xfade, and other primitives."""

from typing import Literal

import numpy as np

Curve = Literal["linear", "log", "exp", "qsin"]


def make_envelope(vol_start: float, vol_end: float, num_samples: int, curve: Curve) -> np.ndarray:
    """Return a volume envelope array of shape (num_samples,) going from vol_start to vol_end.

    Used by fade (arbitrary vol_start/vol_end) and xfade (always 0→1 or 1→0).

    Curves:
        linear — straight line
        log    — logarithmic (perceptually even for volume control)
        exp    — exponential (slow start, fast end)
        qsin   — quarter-sine S-curve (equal-power crossfade when used as 0→1 / 1→0 pair)
    """
    match curve:
        case "linear":
            return np.linspace(vol_start, vol_end, num_samples)
        case "log":
            if vol_start <= 0 or vol_end <= 0:
                raise ValueError(
                    f"log curve requires vol_start and vol_end > 0, got vol_start={vol_start}, vol_end={vol_end} — use 'linear' or 'qsin' for fades to/from silence"
                )
            return np.geomspace(vol_start, vol_end, num_samples)
        case "exp":
            return np.linspace(0, 1, num_samples) ** 2 * (vol_end - vol_start) + vol_start
        case "qsin":
            return (
                np.sin(np.linspace(0, np.pi / 2, num_samples)) * (vol_end - vol_start) + vol_start
            )
        case _:
            raise ValueError(f"Unknown curve: {curve!r}. Must be one of {Curve}.")
