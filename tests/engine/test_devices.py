"""A8: every device has an audible, correctly signed effect; automation reaches the parameters."""

import numpy as np
import pytest

from recut import devices as D
from recut.contracts.plan import (
    AutoFilter,
    Delay,
    Eq,
    EqBand,
    Limiter,
    Points,
    Ramp,
    Reverb,
    Utility,
)

SR = 44100


def noise(seconds=2.0, amp=0.1, seed=0):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal((2, int(seconds * SR))) * amp).astype(np.float32)


def band_db(x, lo, hi):
    """Energy (dB) of a mono mix of x between lo and hi Hz."""
    spec = np.abs(np.fft.rfft(x.mean(axis=0))) ** 2
    f = np.fft.rfftfreq(x.shape[-1], 1 / SR)
    return 10 * np.log10(spec[(f >= lo) & (f < hi)].sum() + 1e-20)


def ctx(autos=(), length=2.0, bpm=120.0):
    return D.Ctx(SR, bpm, 4, length, list(autos))


def run(dev, x, **kw):
    return D.apply_devices([dev], x, ctx(**kw))


def test_utility_gain_and_width():
    x = noise()
    y = run(Utility(type="utility", id="u", gain=-6), x)
    assert np.allclose(y, x * 10 ** (-6 / 20), atol=1e-6)
    mono = run(Utility(type="utility", id="u", width=0), x)
    assert np.allclose(mono[0], mono[1], atol=1e-6)  # width 0 = mono
    wide = run(Utility(type="utility", id="u", width=200), x)
    side = lambda a: np.abs(a[0] - a[1]).mean()  # noqa: E731
    assert side(wide) > 1.9 * side(x)


def test_eq_cuts_and_bands():
    x = noise()
    hp = run(Eq(type="eq", id="e", low_cut=2000), x)
    assert band_db(x, 20, 300) - band_db(hp, 20, 300) > 12
    assert abs(band_db(x, 5000, 9000) - band_db(hp, 5000, 9000)) < 1.5  # passband untouched
    lp = run(Eq(type="eq", id="e", high_cut=1000), x)
    assert band_db(x, 4000, 8000) - band_db(lp, 4000, 8000) > 12
    boost = run(Eq(type="eq", id="e", bands=[EqBand(frequency=1000, gain=9, q=1.0)]), x)
    cut = run(Eq(type="eq", id="e", bands=[EqBand(frequency=1000, gain=-9, q=1.0)]), x)
    assert band_db(boost, 900, 1100) - band_db(x, 900, 1100) > 5
    assert band_db(x, 900, 1100) - band_db(cut, 900, 1100) > 5


def test_auto_filter_lowpass_highpass_bandpass():
    x = noise()
    lp = run(AutoFilter(type="auto_filter", id="f", filter="lowpass", frequency=500), x)
    assert band_db(x, 2000, 10000) - band_db(lp, 2000, 10000) > 12
    hp = run(AutoFilter(type="auto_filter", id="f", filter="highpass", frequency=5000), x)
    assert band_db(x, 50, 800) - band_db(hp, 50, 800) > 12
    bp = run(AutoFilter(type="auto_filter", id="f", filter="bandpass", frequency=1000), x)
    assert band_db(bp, 800, 1250) - band_db(bp, 6000, 12000) > 12
    res = run(AutoFilter(type="auto_filter", id="f", filter="lowpass", frequency=1000, resonance=1.0), x)
    plain = run(AutoFilter(type="auto_filter", id="f", filter="lowpass", frequency=1000), x)
    assert band_db(res, 800, 1300) > band_db(plain, 800, 1300) + 3  # resonance peaks at the cutoff


def test_auto_filter_frequency_automation_sweeps_down():
    x = noise(4.0)
    au = Ramp(target="devices.f.frequency", from_=20000, to=300, over="2s", shape="linear")
    y = run(AutoFilter(type="auto_filter", id="f", frequency=20000), x, autos=[au], length=4.0)
    first, last = y[:, : SR // 2], y[:, -SR:]  # before the sweep has moved / after it ended
    assert band_db(last, 2000, 10000) < band_db(first, 2000, 10000) - 15


def test_reverb_tail_decay_pre_delay_hi_cut_and_dry_wet():
    burst = np.zeros((2, SR * 8), dtype=np.float32)
    burst[:, :2000] = noise(2000 / SR, 0.3)[:, :2000]
    wet = run(Reverb(type="reverb", id="r", decay="3s", dry_wet=100), burst, length=8.0)
    after = wet[:, SR // 2: SR]
    assert np.abs(after).max() > 1e-3  # rings after the input has ended
    short = run(Reverb(type="reverb", id="r", decay="0.6s", dry_wet=100), burst, length=8.0)
    long_ = run(Reverb(type="reverb", id="r", decay="6s", dry_wet=100), burst, length=8.0)
    e = lambda a: float((a[:, 3 * SR: 4 * SR] ** 2).sum())  # noqa: E731
    assert e(long_) > 20 * e(short)  # longer decay is still ringing at 3 s
    dry = run(Reverb(type="reverb", id="r", decay="3s", dry_wet=0), burst, length=8.0)
    assert np.allclose(dry, burst)
    pre = run(Reverb(type="reverb", id="r", decay="3s", pre_delay="200ms", dry_wet=100), burst, length=8.0)
    assert np.abs(pre[:, 2000: int(0.19 * SR)]).max() < 1e-6  # silent until the pre-delay has passed
    assert np.abs(pre[:, int(0.25 * SR): int(0.5 * SR)]).max() > 1e-4
    bright = run(Reverb(type="reverb", id="r", hi_cut=16000, dry_wet=100), burst, length=8.0)
    dark = run(Reverb(type="reverb", id="r", hi_cut=800, dry_wet=100), burst, length=8.0)
    assert band_db(bright, 4000, 12000) - band_db(dark, 4000, 12000) > 10


def test_reverb_dry_wet_automation_fades_the_wash_in():
    x = noise(4.0)
    au = Ramp(target="devices.r.dry_wet", from_=0, to=100, over="2s", shape="linear", at="start")
    y = run(Reverb(type="reverb", id="r", dry_wet=100), x, autos=[au], length=4.0)
    assert np.allclose(y[:, :1000], x[:, :1000], atol=0.02)  # starts dry
    assert not np.allclose(y[:, -SR:], x[:, -SR:], atol=0.05)  # ends wet


def _echo_energy(y, t, width=0.03):
    a = int(t * SR)
    return float((y[:, a: a + int(width * SR)] ** 2).sum()), y[:, a: a + int(width * SR)]


def test_delay_time_feedback_ping_pong_and_dry_wet():
    imp = np.zeros((2, SR * 3), dtype=np.float32)
    imp[:, 100:140] = 0.5
    flt = dict(filter_lo=20, filter_hi=19000)
    # "1/8" at 120 BPM = 250 ms
    y = run(Delay(type="delay", id="d", time="1/8", feedback=50, dry_wet=100, **flt), imp, length=3.0, bpm=120.0)
    e0, _ = _echo_energy(y, 0.0)
    e1, _ = _echo_energy(y, 0.25 + 100 / SR - 0.005)
    e2, _ = _echo_energy(y, 0.5 + 100 / SR - 0.005)
    e_mid, _ = _echo_energy(y, 0.37)
    assert e0 < 1e-9 and e1 > 0 and e_mid < e1 * 1e-3  # wet only: echoes land on the grid
    assert 0.1 < e2 / e1 < 0.5  # feedback 50% -> second echo about -6 dB in amplitude
    none = run(Delay(type="delay", id="d", time="1/8", feedback=0, dry_wet=100, **flt), imp, length=3.0)
    assert _echo_energy(none, 0.5 + 100 / SR - 0.005)[0] < e1 * 1e-3  # feedback 0 -> a single echo
    pp = run(Delay(type="delay", id="d", time="1/8", feedback=60, ping_pong=True, dry_wet=100, **flt), imp,
             length=3.0)
    _, r1 = _echo_energy(pp, 0.25 + 100 / SR - 0.005)
    _, r2 = _echo_energy(pp, 0.5 + 100 / SR - 0.005)
    assert (r1[0] ** 2).sum() > 50 * (r1[1] ** 2).sum()  # echo 1 left
    assert (r2[1] ** 2).sum() > 50 * (r2[0] ** 2).sum()  # echo 2 right
    dry = run(Delay(type="delay", id="d", time="1/8", dry_wet=0), imp, length=3.0)
    assert np.allclose(dry, imp)
    ms = run(Delay(type="delay", id="d", time="400ms", feedback=0, dry_wet=100, **flt), imp, length=3.0)
    assert _echo_energy(ms, 0.4 + 100 / SR - 0.005)[0] > 0


def test_delay_filters_darken_the_repeats():
    x = noise(1.0)
    open_ = run(Delay(type="delay", id="d", time="1/8", feedback=0, filter_hi=19000, filter_lo=20, dry_wet=100), x)
    dark = run(Delay(type="delay", id="d", time="1/8", feedback=0, filter_hi=1000, filter_lo=20, dry_wet=100), x)
    assert band_db(open_, 4000, 12000) - band_db(dark, 4000, 12000) > 12
    thin = run(Delay(type="delay", id="d", time="1/8", feedback=0, filter_hi=19000, filter_lo=3000, dry_wet=100), x)
    assert band_db(open_, 50, 500) - band_db(thin, 50, 500) > 12


def test_limiter_scales_to_ceiling_only_when_over():
    loud = noise(1.0, 0.8)
    c = ctx()
    y = D.apply_devices([Limiter(type="limiter", id="l", ceiling=-6)], loud, c)
    assert c.limited and np.abs(y).max() <= 10 ** (-5.9 / 20)
    quiet = noise(1.0, 0.05)
    c2 = ctx()
    assert np.allclose(D.apply_devices([Limiter(type="limiter", id="l", ceiling=-6)], quiet, c2), quiet)
    assert not c2.limited


def test_gain_points_automation_on_a_utility():
    x = np.ones((2, SR * 2), dtype=np.float32) * 0.5
    au = Points(target="devices.u.gain", points=[("0s", 0), ("1s", -6)], shape="linear")
    y = run(Utility(type="utility", id="u"), x, autos=[au])
    assert y[0, 0] == pytest.approx(0.5, abs=1e-3)
    assert y[0, -1] == pytest.approx(0.5 * 10 ** (-6 / 20), abs=1e-3)  # holds the last point
    assert y[0, SR // 2] == pytest.approx(0.5 * ((1 + 10 ** (-6 / 20)) / 2), abs=2e-3)
