import json

import numpy as np
import pytest

from recut import tickets
from recut.contracts import Plan
from recut.engine import PlanError, render_plan


def load(root, tid, k):
    d = tickets.iteration_dir(tid, 1, k, root)
    return json.loads((d / "plan.json").read_text()), json.loads((d / "render.json").read_text())


def test_medley_segments_and_splices(demo):
    root, tid = demo
    _, r = load(root, tid, 1)
    assert [s["label"] for s in r["segments"]] == ["intro#1", "verse#1", "chorus#1", "inst#1"]
    assert [s["source"] for s in r["segments"]] == ["a", "a", "b", "b"]
    s2 = r["splices"][1]
    assert s2["cross_source"] and s2["from"] == "n2" and s2["to"] == "n3"
    beat = 60 / r["sources"]["a"]["bpm"]
    assert s2["overlap_ms"] == pytest.approx(2 * beat * 1000, abs=1)
    # incoming segment starts where the overlap starts
    assert r["segments"][2]["out_start"] == pytest.approx(s2["out_time"])
    assert r["segments"][1]["out_end"] - r["segments"][2]["out_start"] == pytest.approx(2 * beat, abs=1e-3)


def test_hold_overlap_and_unrendered_features_reported(demo):
    root, tid = demo
    _, r = load(root, tid, 2)
    s3 = r["splices"][2]
    assert (s3["overlap_ms"], s3["out_shape"], s3["in_shape"]) == (pytest.approx(30, abs=0.1), "hold", "equal_power")
    rules = {i["rule"] for i in r["issues"]}
    assert "not_rendered" in rules  # sends/automation/returns are A7/A8
    assert r["automation"][0]["target"] == "sends.A"
    seg = r["segments"][2]
    assert r["automation"][0]["out_end"] == pytest.approx(seg["out_end"], abs=1e-3)


def test_render_is_click_free_and_limited(demo):
    root, tid = demo
    plan = Plan.model_validate_json((tickets.iteration_dir(tid, 1, 2, root) / "plan.json").read_text())
    audio, info = render_plan(plan, root / tid)
    jumps = np.abs(np.diff(audio.samples, axis=-1)).max(axis=0)
    # music has sharp transients of its own: a splice may not jump more than the source does
    src_jump = np.abs(np.diff(audio.samples[:, : int(10 * audio.sr)], axis=-1)).max()
    for sp in info.splices:
        i = int(sp.out_time * audio.sr)
        assert jumps[max(0, i - 220): i + 220].max() <= src_jump * 1.05, sp.id
    assert np.abs(audio.samples).max() <= 10 ** (-0.99 / 20)  # limiter ceiling -1 dB
    assert info.limiter_applied


def test_bad_section_is_an_agent_readable_error(demo):
    root, tid = demo
    data = json.loads((tickets.iteration_dir(tid, 1, 1, root) / "plan.json").read_text())
    data["tracks"][0]["clips"][0]["segment"] = "outro"
    with pytest.raises(PlanError, match="Sections in source 'a'"):
        render_plan(Plan.model_validate(data), root / tid)


def test_too_many_bars_is_an_error(demo):
    root, tid = demo
    data = json.loads((tickets.iteration_dir(tid, 1, 1, root) / "plan.json").read_text())
    data["tracks"][0]["clips"][0]["bars"] = 40
    with pytest.raises(PlanError, match="bars"):
        render_plan(Plan.model_validate(data), root / tid)
