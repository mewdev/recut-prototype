import numpy as np

from recut.audio import Audio
from recut.primitives.curves import Curve, make_envelope


def xfade(xfade_ms: float = 500, curve: Curve = "qsin"):
    """
    xfade_ms : crossfade duration in milliseconds
                overlap region: end of a fades out, start of b fades in
                output length = len(a) + len(b) - xfade_samples
    curve    : fade shape — "linear" | "log" | "exp" | "qsin"
                qsin (quarter-sine) gives equal-power crossfade — best default for music
    """

    def apply(a: Audio, b: Audio) -> Audio:
        if a.sr != b.sr:
            raise ValueError(
                f"xfade requires matching sample rates: a.sr={a.sr}, b.sr={b.sr} — resample before crossfading"
            )
        xfade_samples = int(xfade_ms * a.sr / 1000)

        if xfade_samples >= a.num_samples or xfade_samples >= b.num_samples:
            raise ValueError(
                f"xfade_ms={xfade_ms} longer than one segment "
                f"(a={a.num_samples} samples, b={b.num_samples} samples)"
            )

        fade_in_ramp = make_envelope(0.0, 1.0, xfade_samples, curve)
        fade_out_ramp = make_envelope(1.0, 0.0, xfade_samples, curve)

        def combine(ach, bch):
            a_body = ach[:-xfade_samples]
            a_tail = ach[-xfade_samples:]
            b_head = bch[:xfade_samples]
            b_tail = bch[xfade_samples:]

            overlap = a_tail * fade_out_ramp + b_head * fade_in_ramp
            return np.concatenate([a_body, overlap, b_tail])

        if a.num_channels != b.num_channels:
            raise ValueError(
                f"xfade requires matching channel layout: a has {a.num_channels} ch, b has {b.num_channels} ch"
            )

        if a.is_mono:
            return Audio(combine(a.samples, b.samples), a.sr)
        return Audio(
            np.stack([combine(ach, bch) for ach, bch in zip(a.samples, b.samples)]),
            a.sr,
        )

    return apply
