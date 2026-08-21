"""Tests for primitives using synthetic audio — no file I/O."""

import numpy as np
import pytest

from recut.audio import Audio
from recut.compositor import Clip, compose
from recut.map.parser import parse_recut_map
from recut.primitives.chain import chain
from recut.primitives.curves import make_envelope
from recut.primitives.cut import cut
from recut.primitives.fade import fade
from recut.primitives.xfade import xfade

MAP = "tests/fixtures/sample-map.json"


# --- Helpers ---------------------------------------------------------------


def make_audio(duration_s: float = 2.0, sr: int = 44100, channels: int = 2) -> Audio:
    samples = np.ones((channels, int(duration_s * sr)))
    return Audio(samples, sr)


def make_mono(duration_s: float = 2.0, sr: int = 44100) -> Audio:
    samples = np.ones(int(duration_s * sr))
    return Audio(samples, sr)


# --- cut -------------------------------------------------------------------


def test_cut_output_duration():
    audio = make_audio(2.0)
    result = cut(0.5, 1.5)(audio)
    assert result.num_samples == pytest.approx(int(1.0 * 44100), abs=2)


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
    assert result.samples[0, 0] < 0.01


def test_chain_no_transforms():
    audio = make_audio(1.0)
    result = chain(audio)
    assert result.num_samples == audio.num_samples


# --- compose fx ------------------------------------------------------------


def test_clip_fx_applied(music_map_fixture):
    audio = make_audio(4.0)
    result = compose(
        music_map_fixture,
        audio,
        Clip("intro", fx=[fade(vol_start=0.0, vol_end=1.0)]),
    )
    assert result.samples[0, 0] < 0.01   # fade-in: start silent
    assert result.samples[0, -1] > 0.9   # end loud


def test_clip_loop_doubles_duration(music_map_fixture):
    audio = make_audio(4.0)
    no_loop = compose(music_map_fixture, audio, Clip("intro"))
    looped = compose(music_map_fixture, audio, Clip("intro", loop=2))
    assert looped.num_samples == pytest.approx(no_loop.num_samples * 2, abs=4)


def test_loop_fx_applies_post_concat(music_map_fixture):
    """fx sees the full looped clip — fade spans both repetitions."""
    audio = make_audio(4.0)
    result = compose(
        music_map_fixture,
        audio,
        Clip("intro", loop=2, fx=[fade(vol_start=0.0, vol_end=1.0)]),
    )
    assert result.samples[0, 0] < 0.01
    assert result.samples[0, -1] > 0.9


# --- xfade ----------------------------------------------------------------


def test_xfade_output_length():
    a = make_audio(2.0)
    b = make_audio(2.0)
    xfade_ms = 500
    result = xfade(xfade_ms)(a, b)
    xfade_samples = int(xfade_ms * a.sr / 1000)
    expected = a.num_samples + b.num_samples - xfade_samples
    assert result.num_samples == expected


def test_xfade_sr_mismatch_raises():
    a = make_audio(2.0, sr=44100)
    b = make_audio(2.0, sr=48000)
    with pytest.raises(ValueError, match="sample rates"):
        xfade(500)(a, b)


def test_xfade_too_long_raises():
    a = make_audio(1.0)  # 44100 samples
    b = make_audio(1.0)
    with pytest.raises(ValueError):
        xfade(1000)(a, b)  # 1000ms == full clip length, should reject


def test_xfade_channel_mismatch_raises():
    a = make_audio(2.0, channels=2)
    b = make_mono(2.0)
    with pytest.raises(ValueError, match="channel"):
        xfade(500)(a, b)


def test_xfade_preserves_sr():
    a = make_audio(2.0, sr=44100)
    b = make_audio(2.0, sr=44100)
    result = xfade(500)(a, b)
    assert result.sr == 44100


def test_xfade_mono():
    a = make_mono(2.0)
    b = make_mono(2.0)
    result = xfade(500)(a, b)
    assert result.is_mono


# --- curves ---------------------------------------------------------------


def test_make_envelope_log_raises_on_zero():
    with pytest.raises(ValueError, match="log curve"):
        make_envelope(0.0, 1.0, 100, "log")


def test_make_envelope_log_raises_on_negative():
    with pytest.raises(ValueError, match="log curve"):
        make_envelope(-0.5, 1.0, 100, "log")


def test_make_envelope_unknown_curve_raises():
    with pytest.raises(ValueError, match="Unknown curve"):
        make_envelope(0.0, 1.0, 100, "banana")  # type: ignore


def test_make_envelope_linear_endpoints():
    env = make_envelope(0.0, 1.0, 100, "linear")
    assert env[0] == pytest.approx(0.0, abs=1e-6)
    assert env[-1] == pytest.approx(1.0, abs=1e-6)


@pytest.fixture
def music_map_fixture():
    return parse_recut_map(MAP)
