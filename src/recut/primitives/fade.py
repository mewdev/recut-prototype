from recut.audio import Audio
from recut.primitives.curves import Curve, make_envelope


def fade(vol_start: float = 0.0, vol_end: float = 1.0, curve: Curve = "linear"):
    """
    vol_start: volume at beginning, 0.0 silence, 1.0 default volume
    vol_end:   volume at end, 1.0 default volume, 0.0 silence
    curve:     shape of the fade, options: linear, log, exp, qsin
    """

    def apply(audio: Audio) -> Audio:
        envelope = make_envelope(vol_start, vol_end, audio.num_samples, curve)
        return audio.apply_to_channels(lambda ch: ch * envelope)

    return apply
