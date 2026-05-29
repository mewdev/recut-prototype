"""
reverb(audio, sr, wetness, reverb_type, room_size, damping, width) → np.ndarray

Apply reverb to audio using Spotify's pedalboard library (proper DSP).

Parameters
----------
wetness     : 0.0–1.0 — mix of dry vs wet signal (0 = dry only, 1 = wet only)
reverb_type : "room" | "hall" | "plate" — preset that sets room_size/damping/width
              Individual params below override the preset if provided.
room_size   : 0.0–1.0 — size of simulated space (overrides preset)
damping     : 0.0–1.0 — high-freq absorption (0 = bright/live, 1 = dark/dead)
width       : 0.0–1.0 — stereo spread of the reverb tail

Presets
-------
room  — small, intimate  (room_size=0.35, damping=0.7,  width=0.5)
hall  — large, spacious  (room_size=0.85, damping=0.3,  width=0.9)
plate — bright, washed   (room_size=0.6,  damping=0.1,  width=1.0)
"""

import numpy as np
from pedalboard import Reverb, Pedalboard


PRESETS = {
    "room":  dict(room_size=0.35, damping=0.7,  width=0.5),
    "hall":  dict(room_size=0.85, damping=0.3,  width=0.9),
    "plate": dict(room_size=0.6,  damping=0.1,  width=1.0),
}


def reverb(
    audio: np.ndarray,
    sr: int,
    wetness: float = 0.4,
    reverb_type: str = "hall",
    room_size: float = None,
    damping: float = None,
    width: float = None,
) -> np.ndarray:
    preset = PRESETS.get(reverb_type, PRESETS["hall"]).copy()
    if room_size is not None: preset["room_size"] = room_size
    if damping   is not None: preset["damping"]   = damping
    if width     is not None: preset["width"]      = width

    board = Pedalboard([
        Reverb(
            room_size=preset["room_size"],
            damping=preset["damping"],
            wet_level=wetness,
            dry_level=1.0 - wetness,
            width=preset["width"],
        )
    ])

    # pedalboard expects (channels, samples) float32
    mono = audio.ndim == 1
    sig = audio[np.newaxis, :].astype(np.float32) if mono else audio.astype(np.float32)
    out = board(sig, sr)
    return out[0] if mono else out
