"""Gap (pause) node, multi-track layering and stem files as sources (PLAN §3.2, 2026-11-18)."""

import copy
import json
import shutil

import numpy as np
import pytest
from pydantic import ValidationError

from recut import tickets
from recut.contracts import Plan
from recut.engine import render_plan


@pytest.fixture
def base(demo):
    root, tid = demo
    return root / tid, json.loads((tickets.iteration_dir(tid, 1, 2, root) / "plan.json").read_text())


def plan(base_plan, *tracks, **extra):
    d = copy.deepcopy(base_plan)
    d["tracks"] = [{"id": tid, "clips": clips, **kw} for tid, clips, kw in tracks]
    d.pop("target_duration_s", None)
    d["master"] = {"devices": []}  # no limiter: sums stay linear
    d.update(extra)
    return Plan.model_validate(d)


def clip(i, seg="verse", idx=1, **kw):
    return {"id": i, "type": "clip", "source": "a", "segment": seg, "index": idx, "bars": 2, **kw}


def gap(i, length):
    return {"id": i, "type": "gap", "length": length}


def rms_db(x):
    return 20 * np.log10(max(float(np.sqrt((x ** 2).mean())), 1e-9))


def test_gap_is_silence_and_nothing_joins_across_it(base):
    d, p = base
    audio, info = render_plan(plan(p, ("main", [clip("n1"), gap("g", "2s"), clip("n2")], {})), d)
    a, b = info.segments
    assert b.out_start == pytest.approx(a.out_end + 2.0, abs=1e-3)
    assert info.splices == []
    assert not [i for i in info.issues if i.rule == "qc_gap"]  # a planned pause is not a defect
    sr = audio.sr
    assert rms_db(audio.samples[:, int((a.out_end + 0.1) * sr): int((b.out_start - 0.1) * sr)]) < -90


def test_return_tail_rings_through_a_gap(base):
    d, p = base
    audio, info = render_plan(plan(p, ("main", [clip("n1", sends={"A": 0}), gap("g", "2s"), clip("n2")], {})), d)
    end, sr = info.segments[0].out_end, audio.sr
    assert rms_db(audio.samples[:, int((end + 0.2) * sr): int((end + 0.7) * sr)]) > -60


def test_gap_length_in_bars_follows_the_previous_clip(base):
    d, p = base
    audio, info = render_plan(plan(p, ("main", [clip("n1"), gap("g", "1 bar"), clip("n2")], {})), d)
    bar = 60 / info.sources["a"].bpm * 4
    assert info.segments[1].out_start - info.segments[0].out_end == pytest.approx(bar, abs=1e-3)


def test_xfade_cannot_touch_a_gap_and_a_track_cannot_end_with_one(base):
    _, p = base
    with pytest.raises(ValidationError, match="can't touch a gap"):
        plan(p, ("main", [clip("n1"), {"id": "x", "type": "xfade"}, gap("g", "1s"), clip("n2")], {}))
    with pytest.raises(ValidationError, match="must end with a clip"):
        plan(p, ("main", [clip("n1"), gap("g", "1s")], {}))


def test_second_track_layers_on_top_from_its_leading_gap(base):
    d, p = base
    main = ("main", [clip("n1", bars=4)], {})
    fx = ("fx", [gap("g", "1s"), clip("f1", "chorus")], {})
    both, info = render_plan(plan(p, main, fx), d)
    only_main, _ = render_plan(plan(p, main), d)
    only_fx, _ = render_plan(plan(p, fx), d)
    f1 = next(s for s in info.segments if s.node_id == "f1")
    assert f1.track == "fx" and f1.out_start == pytest.approx(1.0, abs=1e-3)
    assert {s.track for s in info.segments} == {"main", "fx"}
    n = min(both.samples.shape[-1], only_main.samples.shape[-1], only_fx.samples.shape[-1])
    summed = only_main.samples[:, :n] + only_fx.samples[:, :n]
    assert np.allclose(both.samples[:, :n], summed, atol=1e-4)  # stacked = summed


def test_track_volume_mutes_one_layer(base):
    d, p = base
    main = ("main", [clip("n1", bars=4)], {})
    both, _ = render_plan(plan(p, main, ("fx", [clip("f1", "chorus")], {"volume": "-inf"})), d)
    only_main, _ = render_plan(plan(p, main), d)
    n = min(both.samples.shape[-1], only_main.samples.shape[-1])
    assert np.allclose(both.samples[:, :n], only_main.samples[:, :n], atol=1e-6)


def test_splice_ids_are_unique_across_tracks(base):
    d, p = base
    _, info = render_plan(plan(p, ("main", [clip("n1"), clip("n2")], {}),
                               ("fx", [clip("f1", "chorus"), clip("f2", "chorus")], {})), d)
    ids = [s.id for s in info.splices]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_a_stem_file_with_its_songs_map_is_a_source(base, tmp_path):
    # a stem has the song's timeline, so it uses the song's map (here: a copy of the mix stands in)
    shared, p = base
    d = tmp_path / "ticket"  # own copy: the demo ticket is shared by the whole test session
    shutil.copytree(shared, d)
    src = p["sources"]["a"]
    stem = d / "stems" / "a" / ("vocals" + (d / src["file"]).suffix)
    stem.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(d / src["file"], stem)
    sources = {**p["sources"], "a_vox": {"file": str(stem.relative_to(d)), "map": src["map"]}}
    vox = {**clip("v1", "chorus"), "source": "a_vox"}
    _, info = render_plan(plan(p, ("main", [clip("n1", bars=4)], {}),
                               ("vox", [gap("g", "1 bar"), vox], {}), sources=sources), d)
    v1 = next(s for s in info.segments if s.node_id == "v1")
    assert v1.source == "a_vox" and v1.track == "vox"


def test_layer_entry_loudness_is_reported(base):
    d, p = base
    _, info = render_plan(plan(p, ("main", [clip("n1", bars=4)], {}),
                               ("fx", [gap("g", "1s"), clip("f1", "chorus", gain=-6)], {})), d)
    lv = [i for i in info.issues if i.rule == "layer_level"]
    assert len(lv) == 1 and lv[0].node == "f1" and lv[0].severity == "info"
    assert "enters at 1.00s" in lv[0].message and "LU against main" in lv[0].message


def test_a_layer_does_not_hide_the_main_tracks_ending(base):
    # review finding: an FX layer running past the main track must not mask a mid-section stop
    d, p = base
    main = ("main", [clip("n1", bars=2)], {})  # stops mid-verse, no fade_out
    fx = ("fx", [gap("g", "3s"), clip("f1", "chorus", bars=2, fade_out={"length": "1 beat", "shape": "linear"})], {})
    _, alone = render_plan(plan(p, main), d)
    _, layered = render_plan(plan(p, main, fx), d)
    ending = lambda info: [i.node for i in info.issues if i.rule == "ending"]  # noqa: E731
    assert ending(alone) == ["n1"] and ending(layered) == ["n1"]
    seq = lambda info: sorted(i.message for i in info.issues if i.rule == "structure")  # noqa: E731
    assert seq(alone) and seq(alone) == [m for m in seq(layered) if "f1" not in m]


def test_a_send_on_a_layer_feeds_the_return(base):
    # layers share the returns with the main track: a voice FX's reverb tail rings on
    d, p = base
    main = ("main", [clip("n1", bars=2)], {})
    dry, _ = render_plan(plan(p, main, ("fx", [clip("f1", "chorus", bars=1)], {})), d)
    wet, info = render_plan(plan(p, main, ("fx", [clip("f1", "chorus", bars=1, sends={"A": 0})], {})), d)
    end = max(s.out_end for s in info.segments)
    assert info.returns_tail_end > end + 0.5
    assert wet.samples.shape[-1] > dry.samples.shape[-1]  # the tail extends the render
    tail = wet.samples[:, int((end + 0.1) * wet.sr): int((end + 0.5) * wet.sr)]
    assert rms_db(tail) > -60
