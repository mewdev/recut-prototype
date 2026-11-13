"""A8: old-format compositions load into plan v2; concat and xfade reproduce compose() exactly."""

import numpy as np
import pytest

from recut.compositor import compose
from recut.compositor.effects import Delay, Fade, FilterSweep, Reverb, ReverbSweep
from recut.compositor.nodes import Clip, XFade
from recut.engine import load_sources
from recut.legacy import composition_to_plan, render_legacy
from recut.project import _nodes_from_json, _nodes_to_json


@pytest.fixture(scope="module")
def src(demo):
    root, tid = demo
    return root / tid / "inputs" / "a.mp3", root / tid / "maps" / "a.json"


def run(nodes, src):
    audio, info, lp = render_legacy(nodes, "a", *src)
    return audio, info, lp


def reference(nodes, src):
    audio_path, map_path = src
    lp = composition_to_plan(nodes, "a", audio_path, map_path)
    s = load_sources(lp.plan, audio_path.parent.parent)["a"]
    return compose(s.music_map, s.audio, *nodes)


def test_plain_concat_matches_compose_exactly(src):
    nodes = [Clip("intro", bars=2), Clip("verse", bars=2), Clip("chorus", bars=1, loop=2)]
    got, info, _ = run(nodes, src)
    want = reference(nodes, src)
    assert got.samples.shape == want.samples.shape
    assert np.abs(got.samples - want.samples).max() < 1e-6
    assert [s.node_id for s in info.segments] == ["n1", "n2", "n3"]


@pytest.mark.parametrize("xf", [XFade(ms=500), XFade(ms=137.5, curve="linear"), XFade(beats=2), XFade(ms=80, curve="exp")])
def test_legacy_xfade_matches_compose_exactly(src, xf):
    nodes = [Clip("verse", bars=2), xf, Clip("chorus", bars=2), Clip("inst", bars=1)]
    got, _, lp = run(nodes, src)
    want = reference(nodes, src)
    assert got.samples.shape == want.samples.shape
    assert np.abs(got.samples - want.samples).max() < 1e-6
    assert lp.plan.master.devices == []  # no limiter: samples untouched


def test_saved_composition_json_round_trips_into_a_plan(src):
    nodes = [Clip("verse", bars=2, fx=[Fade(0.0, 1.0, "qsin")]), XFade(ms=250), Clip("chorus", bars=2)]
    restored = _nodes_from_json(_nodes_to_json(nodes))
    lp = composition_to_plan(restored, "a", *src)
    assert lp.plan.version == 2 and len(lp.plan.tracks[0].clips) == 3
    assert lp.plan.tracks[0].clips[1].shape == "equal_power"  # qsin accepted as equal_power


def rms_db(a):
    return 20 * np.log10(max(float(np.sqrt((a**2).mean())), 1e-9))


def test_fade_becomes_a_gain_ramp(src):
    got, _, lp = run([Clip("verse", bars=2, fx=[Fade(0.0, 1.0, "linear")])], src)
    want = reference([Clip("verse", bars=2, fx=[Fade(0.0, 1.0, "linear")])], src)
    assert lp.plan.tracks[0].clips[0].automation[0].target == "gain"
    assert np.abs(got.samples - want.samples).max() < 1e-3
    got, _, _ = run([Clip("verse", bars=2, fx=[Fade(1.0, 0.0, "qsin")])], src)
    assert np.abs(got.samples[:, -20:]).max() < 5e-3 and np.abs(got.samples[:, :2000]).max() > 0.01


def test_reverb_becomes_a_clip_device_with_a_ringing_tail(src):
    nodes = [Clip("verse", bars=2, fx=[Reverb(wetness=0.5, reverb_type="hall")])]
    got, info, lp = run(nodes, src)
    dry = reference([Clip("verse", bars=2)], src)
    assert lp.plan.tracks[0].clips[0].devices[0].type == "reverb"
    assert lp.plan.tracks[0].clips[0].devices[0].dry_wet == pytest.approx(50)
    assert got.samples.shape[-1] > dry.samples.shape[-1]  # tail kept
    assert rms_db(got.samples[:, dry.samples.shape[-1]: dry.samples.shape[-1] + 22050]) > -60


def test_reverb_sweep_starts_dry_and_ends_wet(src):
    nodes = [Clip("verse", bars=2, fx=[ReverbSweep(0.0, 0.8, "plate")])]
    got, _, lp = run(nodes, src)
    dry = reference([Clip("verse", bars=2)], src)
    n = dry.samples.shape[-1]
    assert np.abs(got.samples[:, :500] - dry.samples[:, :500]).max() < 5e-3
    assert not np.allclose(got.samples[:, n - 22050: n], dry.samples[:, n - 22050: n], atol=0.02)
    assert lp.plan.tracks[0].clips[0].automation[0].target.endswith(".dry_wet")


def test_delay_becomes_an_echo(src):
    nodes = [Clip("verse", bars=2, fx=[Delay(delay_seconds=0.3, feedback=0.4, mix=0.5)])]
    got, _, lp = run(nodes, src)
    dev = lp.plan.tracks[0].clips[0].devices[0]
    assert (dev.type, dev.time, dev.feedback, dev.dry_wet) == ("delay", "300ms", pytest.approx(40), pytest.approx(50))
    dry = reference([Clip("verse", bars=2)], src)
    assert got.samples.shape[-1] >= dry.samples.shape[-1]
    assert not np.allclose(got.samples[:, : dry.samples.shape[-1]], dry.samples, atol=1e-3)


def test_filter_sweep_darkens_the_clip(src):
    nodes = [Clip("chorus", bars=2, fx=[FilterSweep("low", freq_start=18000, freq_end=300)])]
    got, _, lp = run(nodes, src)
    dry = reference([Clip("chorus", bars=2)], src)
    hf = lambda a: float(np.abs(np.diff(a, axis=-1)).mean())  # noqa: E731
    n = dry.samples.shape[-1]
    assert hf(got.samples[:, n - 22050: n]) < 0.4 * hf(dry.samples[:, n - 22050: n])
    assert lp.plan.tracks[0].clips[0].devices[0].type == "auto_filter"
