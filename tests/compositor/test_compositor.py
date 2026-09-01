"""Tests for compose()-level behavior not covered by primitive/Clip fx tests."""

import numpy as np

from recut.audio import Audio
from recut.compositor import _reverb_tail_padding
from recut.compositor.effects import Reverb


def make_noise(duration_s: float = 1.0, sr: int = 44100, channels: int = 2) -> Audio:
    rng = np.random.default_rng(0)
    samples = rng.uniform(-0.3, 0.3, (channels, int(duration_s * sr))).astype("float32")
    return Audio(samples, sr)


# --- _reverb_tail_padding ----------------------------------------------------


def test_reverb_tail_padding_extends_length():
    audio = make_noise(1.0)
    padded = _reverb_tail_padding(audio, Reverb(reverb_type="room"))
    assert padded.num_samples > audio.num_samples


def test_reverb_tail_padding_no_discontinuity_at_seam():
    # regression: appending silence directly onto real (non-zero-ending) audio
    # is a hard jump — a click, before any fx even runs. Must taper instead.
    audio = make_noise(1.0)
    padded = _reverb_tail_padding(audio, Reverb(reverb_type="room"))
    boundary = audio.num_samples
    step = np.abs(padded.samples[:, boundary] - padded.samples[:, boundary - 1]).max()
    assert step < 0.01


def test_reverb_tail_padding_ends_in_silence():
    audio = make_noise(1.0)
    padded = _reverb_tail_padding(audio, Reverb(reverb_type="room"))
    assert np.all(padded.samples[:, -10:] == 0.0)
