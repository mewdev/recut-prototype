"""Tests for primitives using synthetic audio — no file I/O."""

import numpy as np
import pytest

from audio import Audio
from primitives.chain import chain
from primitives.cut import cut
from primitives.fade import fade

# --- Helpers ---------------------------------------------------------------


def make_audio(duration_s: float = 2.0, sr: int = 44100, channels: int = 2) -> Audio:
    """Synthetic stereo audio filled with ones."""
    samples = np.ones((channels, int(duration_s * sr)))
    return Audio(samples, sr)


def make_mono(duration_s: float = 2.0, sr: int = 44100) -> Audio:
    samples = np.ones(int(duration_s * sr))
    return Audio(samples, sr)


# --- cut -------------------------------------------------------------------


def test_cut_output_duration():
    audio = make_audio(2.0)
    result = cut(0.5, 1.5)(audio)
    expected_samples = int(1.0 * 44100)
    assert result.num_samples == pytest.approx(expected_samples, abs=2)


def test_cut_start_zero():
    audio = make_audio(2.0)
    result = cut(0.0, 1.0)(audio)
    assert result.num_samples == pytest.approx(44100, abs=2)


def test_cut_preserves_channels():
    audio = make_audio(2.0, channels=2)
    result = cut(0.0, 1.0)(audio)
    assert result.samples.shape[0] == 2


def test_cut_mono():
    audio = make_mono(2.0)
    result = cut(0.0, 1.0)(audio)
    assert result.is_mono
    assert result.num_samples == pytest.approx(44100, abs=2)


def test_cut_preserves_sr():
    audio = make_audio(2.0, sr=48000)
    result = cut(0.0, 1.0)(audio)
    assert result.sr == 48000


# --- fade ------------------------------------------------------------------


def test_fade_in_starts_silent():
    audio = make_audio(1.0)
    result = fade(vol_start=0.0, vol_end=1.0)(audio)
    # first sample should be near 0
    assert result.samples[0, 0] < 0.01


def test_fade_out_ends_silent():
    audio = make_audio(1.0)
    result = fade(vol_start=1.0, vol_end=0.0)(audio)
    assert result.samples[0, -1] < 0.01


def test_fade_preserves_shape():
    audio = make_audio(1.0)
    result = fade(vol_start=0.0, vol_end=1.0)(audio)
    assert result.samples.shape == audio.samples.shape


def test_fade_full_volume_unchanged():
    audio = make_audio(1.0)
    result = fade(vol_start=1.0, vol_end=1.0)(audio)
    np.testing.assert_allclose(result.samples, audio.samples, rtol=1e-5)


# --- chain -----------------------------------------------------------------


def test_chain_single_transform():
    audio = make_audio(2.0)
    result = chain(audio, cut(0.0, 1.0))
    assert result.num_samples == pytest.approx(44100, abs=2)


def test_chain_multiple_transforms():
    audio = make_audio(2.0)
    result = chain(audio, cut(0.0, 1.0), fade(vol_start=0.0, vol_end=1.0))
    assert result.num_samples == pytest.approx(44100, abs=2)
    assert result.samples[0, 0] < 0.01  # fade in applied


def test_chain_no_transforms():
    audio = make_audio(1.0)
    result = chain(audio)
    assert result.num_samples == audio.num_samples
