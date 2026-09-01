from typing import Literal

import numpy as np
from pedalboard import Pedalboard, Reverb  # type: ignore

from recut.audio import Audio
from recut.primitives.curves import Curve, make_envelope

ReverbType = Literal["room", "hall", "plate"]

PRESETS = {
    "room": dict(room_size=0.35, damping=0.7, width=0.5),
    "hall": dict(room_size=0.85, damping=0.3, width=0.9),
    "plate": dict(room_size=0.6, damping=0.1, width=1.0),
}


def reverb(
    wetness: float = 0.4,
    reverb_type: ReverbType = "hall",
    room_size: float | None = None,
    damping: float | None = None,
    width: float | None = None,
):
    """
    wetness     : 0.0–1.0 — dry/wet mix (0 = dry only, 1 = fully wet)
    reverb_type : "room" | "hall" | "plate" — preset
    room_size   : 0.0–1.0 — overrides preset (size of simulated space)
    damping     : 0.0–1.0 — overrides preset (0 = bright, 1 = dark/dead)
    width       : 0.0–1.0 — overrides preset (stereo spread of tail)
    """

    def apply(audio: Audio) -> Audio:
        preset = PRESETS[reverb_type].copy()
        if room_size is not None:
            preset["room_size"] = room_size
        if damping is not None:
            preset["damping"] = damping
        if width is not None:
            preset["width"] = width

        board = Pedalboard(
            [
                Reverb(
                    room_size=preset["room_size"],
                    damping=preset["damping"],
                    wet_level=wetness,
                    dry_level=1.0 - wetness,
                    width=preset["width"],
                )
            ]
        )

        out = board(audio.samples.astype("float32"), audio.sr)
        return Audio(out, audio.sr)

    return apply


def reverb_sweep(
    wetness_start: float = 0.0,
    wetness_end: float = 0.4,
    reverb_type: ReverbType = "hall",
    room_size: float | None = None,
    damping: float | None = None,
    width: float | None = None,
    duration: float | None = None,
    curve: Curve = "qsin",
):
    """
    Like reverb(), but the wet/dry mix ramps from wetness_start to wetness_end
    instead of a fixed wetness — fixes the "reverb suddenly appears" onset a
    constant-wetness Reverb produces when it starts partway through a
    composition (dry/wet cross-mixed with an envelope, not automated inside
    pedalboard — pedalboard's wet_level/dry_level are fixed per render call).

    wetness_start/wetness_end : 0.0-1.0 mix at the start/end of the ramp
    duration                  : seconds the ramp takes; None = ramps across the
                                 whole clip. If shorter than the clip, holds at
                                 wetness_end for the remainder.
    curve                     : envelope shape, see curves.make_envelope —
                                 "log" requires both bounds > 0, so it can't
                                 start from full silence.
    """

    def apply(audio: Audio) -> Audio:
        preset = PRESETS[reverb_type].copy()
        if room_size is not None:
            preset["room_size"] = room_size
        if damping is not None:
            preset["damping"] = damping
        if width is not None:
            preset["width"] = width

        board = Pedalboard(
            [
                Reverb(
                    room_size=preset["room_size"],
                    damping=preset["damping"],
                    wet_level=1.0,
                    dry_level=0.0,
                    width=preset["width"],
                )
            ]
        )
        dry = audio.samples.astype("float32")
        wet = board(dry, audio.sr)

        ramp_samples = min(
            int((duration or audio.num_samples / audio.sr) * audio.sr), audio.num_samples
        )
        env = make_envelope(wetness_start, wetness_end, ramp_samples, curve)
        if ramp_samples < audio.num_samples:
            env = np.concatenate(
                [env, np.full(audio.num_samples - ramp_samples, wetness_end, dtype=env.dtype)]
            )

        return Audio(dry * (1.0 - env) + wet * env, audio.sr)

    return apply
