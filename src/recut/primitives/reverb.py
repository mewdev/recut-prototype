from typing import Literal

from pedalboard import Pedalboard, Reverb  # type: ignore

from recut.audio import Audio

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
