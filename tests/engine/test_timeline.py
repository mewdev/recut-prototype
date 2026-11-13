"""A7: timeline engine: returns/sends, tails, track volume/pan, master limiter, legacy xfade."""

import copy
import json

import numpy as np
import pytest

from recut import tickets
from recut.compositor import Clip, XFade, compose
from recut.contracts import Plan
from recut.engine import PlanError, load_sources, render_plan


@pytest.fixture
def base(demo):
    root, tid = demo
    return root / tid, json.loads((tickets.iteration_dir(tid, 1, 2, root) / "plan.json").read_text())


def _plan(clips, base_plan, **extra):
    d = copy.deepcopy(base_plan)
    d["tracks"][0]["clips"] = clips
    d.pop("target_duration_s", None)
    d.update(extra)
    return Plan.model_validate(d)


def clip(i, seg, idx=1, **kw):
    return {"id": i, "type": "clip", "source": "a", "segment": seg, "index": idx, **kw}


def db(x):
    return 20 * np.log10(max(float(x), 1e-9))


def test_send_leaves_return_energy_after_the_clip_ends(base):
    d, p = base
    quiet = [clip("n1", "verse", bars=2, gain=-12, sends={"A": 0})]
    audio, info = render_plan(_plan(quiet, p), d)
    end = info.segments[0].out_end
    after = audio.samples[:, int(end * audio.sr): int((end + 1.0) * audio.sr)]
    assert db(np.sqrt((after**2).mean())) > -40  # the reverb rings on
    assert info.duration_s > end + 1.0 and info.returns_tail_end > end + 1.0
    dry, dinfo = render_plan(_plan([clip("n1", "verse", bars=2, gain=-12)], p), d)
    assert dry.samples.shape[-1] / dry.sr == pytest.approx(end, abs=0.01)
    assert dinfo.returns_tail_end is None


def test_send_opened_on_last_beat_only_rings_after_it(base):
    d, p = base
    auto = [{"target": "sends.A", "from": "-inf", "to": 0, "over": "1 beat", "at": "end", "shape": "exp"}]
    clips = [clip("n1", "verse", bars=2, sends={"A": "-inf"}, automation=auto)]
    audio, info = render_plan(_plan(clips, p), d)
    assert info.automation[0].target == "sends.A"
    assert info.automation[0].out_end == pytest.approx(info.segments[0].out_end, abs=1e-3)
    beat = 60 / info.sources["a"].bpm
    assert info.returns_tail_end > info.segments[0].out_end
    # nothing on the return before the last beat: render with the return muted and compare
    mute = _plan(clips, p)
    mute.returns[0].volume = "-inf"
    ref, _ = render_plan(mute, d)
    n = int((info.segments[0].out_end - beat) * audio.sr)
    assert np.abs(audio.samples[:, :n] - ref.samples[:, :n]).max() < 1e-6


def test_hold_both_sides_keeps_full_level_in_the_overlap(base):
    d, p = base
    both = {"id": "x", "type": "xfade", "length": "200ms", "out_shape": "hold", "in_shape": "hold"}
    clips = [clip("n1", "verse", bars=1, gain=-20), both, clip("n2", "verse", bars=1, gain=-20)]
    audio, info = render_plan(_plan(clips, p, master={"devices": []}), d)
    single, _ = render_plan(_plan(clips[:1], p, master={"devices": []}), d)
    assert info.splices[0].overlap_ms == pytest.approx(200, abs=0.1)
    s2 = info.segments[1].out_start
    i0 = int(round(s2 * audio.sr))
    n = int(0.2 * audio.sr)
    both_full = single.samples[:, -n:] + single.samples[:, :n]  # outgoing tail + incoming head
    assert np.abs(audio.samples[:, i0:i0 + n] - both_full).max() < 1e-5


def test_limiter_only_applied_when_the_peak_is_too_high(base):
    d, p = base
    quiet, qi = render_plan(_plan([clip("n1", "verse", bars=2, gain=-24)], p), d)
    assert not qi.limiter_applied and qi.peak_dbfs < -1
    raw, _ = render_plan(_plan([clip("n1", "verse", bars=2, gain=-24)], p, master={"devices": []}), d)
    assert np.allclose(quiet.samples, raw.samples)  # untouched
    loud, li = render_plan(_plan([clip("n1", "chorus", bars=2, gain=12)], p), d)
    assert li.limiter_applied
    assert li.peak_dbfs == pytest.approx(-1.0, abs=0.05) and np.abs(loud.samples).max() <= 10 ** (-0.99 / 20)


def test_peak_clip_warns_when_overlaps_sum_past_0dbfs(base):
    d, p = base
    both = {"id": "x", "type": "xfade", "length": "1 bar", "out_shape": "hold", "in_shape": "hold"}
    clips = [clip("n1", "chorus", bars=4, gain=6), both, clip("n2", "chorus", bars=4, gain=6)]
    _, info = render_plan(_plan(clips, p), d)
    assert "peak_clip" in {i.rule for i in info.issues}


def test_track_volume_and_constant_power_pan(base):
    d, p = base
    ref, _ = render_plan(_plan([clip("n1", "verse", bars=1, gain=-20)], p, master={"devices": []}), d)
    q = _plan([clip("n1", "verse", bars=1, gain=-20)], p, master={"devices": []})
    q.tracks[0].volume = -6.0
    a, _ = render_plan(q, d)
    assert np.allclose(a.samples, ref.samples * 10 ** (-6 / 20), atol=1e-6)
    q.tracks[0].volume, q.tracks[0].pan = 0.0, -50.0
    left, _ = render_plan(q, d)
    assert np.abs(left.samples[1]).max() < 1e-6 and np.abs(left.samples[0]).max() > 0
    q.tracks[0].pan = 0.0
    centre, _ = render_plan(q, d)
    assert np.allclose(centre.samples, ref.samples)
    q.tracks[0].pan = 25.0  # constant power: L^2 + R^2 gains sum to 2 at any position
    half, _ = render_plan(q, d)
    gl, gr = np.sqrt(2) * np.cos(3 * np.pi / 8), np.sqrt(2) * np.sin(3 * np.pi / 8)
    assert gl**2 + gr**2 == pytest.approx(2)
    assert np.allclose(half.samples, ref.samples * np.array([[gl], [gr]]), atol=1e-6)


def test_return_volume_and_unknown_automation_target(base):
    d, p = base
    bad = _plan([clip("n1", "verse", bars=1, automation=[
        {"target": "sends.Z", "from": "-inf", "to": 0, "over": "1 beat"}])], p)
    with pytest.raises(PlanError, match="unknown automation target"):
        render_plan(bad, d)


def test_legacy_concat_and_xfade_match_compose(base):
    d, p = base
    plan = _plan([clip("n1", "intro", bars=2), clip("n2", "verse", bars=2),
                  {"id": "x", "type": "xfade", "length": "500ms"}, clip("n3", "chorus", bars=2)],
                 p, master={"devices": []})
    src = load_sources(plan, d)["a"]
    want = compose(src.music_map, src.audio,
                   Clip("intro", bars=2), Clip("verse", bars=2), XFade(ms=500, curve="qsin"), Clip("chorus", bars=2))
    got, info = render_plan(plan, d, _legacy_xfades={"x": (500.0, "qsin")})
    assert got.samples.shape == want.samples.shape
    assert np.abs(got.samples - want.samples).max() < 1e-6
    assert info.splices[1].out_shape == "qsin"
    plain = _plan([clip("n1", "intro", bars=2), clip("n2", "verse", bars=2)], p, master={"devices": []})
    want = compose(src.music_map, src.audio, Clip("intro", bars=2), Clip("verse", bars=2))
    assert np.abs(render_plan(plain, d)[0].samples - want.samples).max() < 1e-6
