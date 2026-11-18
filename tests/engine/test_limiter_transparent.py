"""The master limiter must not change audio that stays under its ceiling.

Regression 20261118-fzsv (also seen on -ypag, -idzo): the default master limiter was JUCE's,
a 4:1 compressor above -10 dBFS with make-up gain. A "trim the end" plan came out +3.6 dB
louder in quiet passages and squashed in loud ones, though nobody edited them.
"""

import json
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from recut.contracts import Plan
from recut.devices import _true_peak_env, exact_true_peak, limit
from recut.engine import render_plan

FIXTURE = Path(__file__).parents[1] / "fixtures" / "regressions" / "20261118-fzsv"
SR = 44100


def _db(x):
    return 20 * np.log10(x)


def test_signal_under_the_ceiling_passes_bit_identical():
    t = np.arange(SR) / SR
    for peak_db in (-30, -12, -3, -1.2):
        x = np.tile((10 ** (peak_db / 20) * np.sin(2 * np.pi * 220 * t)).astype(np.float32), (2, 1))
        y, trim = limit(x, SR, -1.0)
        assert np.array_equal(x, y) and trim == 0.0, peak_db


def test_overs_are_caught_locally_and_never_overshoot():
    rng = np.random.default_rng(1)
    x = (0.05 * rng.standard_normal((2, SR * 4))).astype(np.float32)  # peaks ~-14 dBFS
    x[:, SR:SR + 200] *= 30  # one loud burst well over the ceiling
    y, trim = limit(x, SR, -1.0)
    assert _db(exact_true_peak(y, SR)) <= -1.0 + 0.01
    far = np.r_[0:SR - 1000, SR + 1200:x.shape[1]]  # > 20 ms away from the burst
    assert np.array_equal(x[:, far], y[:, far])


def test_chunked_true_peak_matches_one_pass():
    """Chunked measurement = one pass. The old code read each chunk's zero-padded edges, which
    rang up to ~1 dB high on real audio (ticket 20261118-fzsv source: +0.99 dBTP read, -0.26 real)."""
    from scipy import signal
    rng = np.random.default_rng(3)
    x = (0.05 * rng.standard_normal((2, SR * 25))).astype(np.float32)
    t = np.arange(20_000) / SR
    x[:, 470_000:490_000] = 0.5 * np.sin(2 * np.pi * 15000 * t)  # bright and loud across chunk edges
    one_pass = float(np.abs(signal.resample_poly(x, 4, 1, axis=-1))[:, 400:-400].max())
    assert abs(_db(exact_true_peak(x, SR)) - _db(one_pass)) < 0.05


def _loud_master(n: int) -> np.ndarray:
    """A stand-in for a mastered track: dense, quiet verses and loud choruses, sample peaks
    a little over 0 dBFS (like a decoded MP3)."""
    rng = np.random.default_rng(7)
    t = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * t + p) for f, p in ((110, 0), (220, 1), (330, 2), (523, 3)))
    x = x + 0.6 * rng.standard_normal(n)
    level = np.where((t // 20) % 2 == 0, 0.08, 0.25)  # 20 s quiet, 20 s loud
    x = x * level
    x = x / np.abs(x).max() * 10 ** (0.1 / 20)
    return np.tile(x.astype(np.float32), (2, 1))


def test_fzsv_trim_plan_keeps_the_untouched_part_as_the_original(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "t")
    base = tmp_path / "t"
    duration = json.loads((base / "maps" / "a.json").read_text())["duration"]
    src = _loud_master(int(duration * SR))
    (base / "inputs").mkdir()
    sf.write(base / "inputs" / "a.wav", src.T, SR, subtype="FLOAT")
    plan = json.loads((base / "plan.json").read_text())
    plan["sources"]["a"]["file"] = "inputs/a.wav"

    audio, info = render_plan(Plan.model_validate(plan), base, deep_qc=False)
    out = audio.samples

    edited_from = 172.0  # the last clip (inst#3, reverb send, fade) starts at 172.71 s
    n = int(edited_from * SR)
    env = _true_peak_env(src[:, :n], SR)
    near_over = np.convolve(env > 10 ** (-1.05 / 20), np.ones(int(0.04 * SR)), "same") > 0
    keep = ~near_over
    # quiet passages: bit-identical (was +3.6 dB)
    assert np.allclose(out[:, :n][:, keep], src[:, :n][:, keep], atol=1e-6)
    # loud passages: only the samples around overs move, nothing else is squashed
    assert near_over.mean() < 0.5
    assert _db(exact_true_peak(out, SR)) <= -1.0 + 0.01
    assert not any(i.rule == "qc_limiting" for i in info.issues)
