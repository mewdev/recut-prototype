import numpy as np

from audio import Audio


def xfade(xfade_ms: float = 500):
    """
    xfade_ms : crossfade duration in milliseconds
                overlap region: end of a fades out, start of b fades in
                output length = len(a) + len(b) - xfade_samples
    """

    def apply(a: Audio, b: Audio) -> Audio:
        xfade_samples = int(xfade_ms * a.sr / 1000)

        if xfade_samples > a.num_samples or xfade_samples > b.num_samples:
            raise ValueError(
                f"xfade_ms={xfade_ms} longer than one segment "
                f"(a={a.num_samples} samples, b={b.num_samples} samples)"
            )

        fade_out_ramp = np.sqrt(np.linspace(1, 0, xfade_samples))  # 1 -> 0
        fade_in_ramp = np.sqrt(np.linspace(0, 1, xfade_samples))  # 0 -> 1

        def combine(ach, bch):
            a_body = ach[:-xfade_samples]
            a_tail = ach[-xfade_samples:]
            b_head = bch[:xfade_samples]
            b_tail = bch[xfade_samples:]

            overlap = a_tail * fade_out_ramp + b_head * fade_in_ramp
            return np.concatenate([a_body, overlap, b_tail])

        if a.is_mono:
            return Audio(combine(a.samples, b.samples), a.sr)
        return Audio(
            np.stack([combine(ach, bch) for ach, bch in zip(a.samples, b.samples)]),
            a.sr,
        )

    return apply
