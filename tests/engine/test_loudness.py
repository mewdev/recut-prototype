"""A3: LUFS match on load for multi-source plans."""

import json

import numpy as np
import pytest

from recut import tickets
from recut.audio import Audio
from recut.contracts import Plan
from recut.engine import (
    LUFS_CAP,
    LoadedSource,
    _load_audio,
    load_sources,
    match_loudness,
    render_plan,
)
from recut.qc import integrated_lufs

SR = 22050


def tone(db: float, seconds: float = 6.0) -> Audio:
    t = np.arange(int(seconds * SR)) / SR
    x = (10 ** (db / 20)) * np.sin(2 * np.pi * 220 * t).astype(np.float32)
    return Audio(np.stack([x, x]), SR)


def loaded(db: float) -> LoadedSource:
    a = tone(db)
    lufs = integrated_lufs(a.samples, a.sr)
    return LoadedSource(None, a, lufs_in=lufs, lufs_target=lufs)  # type: ignore[arg-type]


def test_two_sources_6db_apart_come_out_level_matched():
    srcs = {"a": loaded(-20), "b": loaded(-26)}
    match_loudness(srcs)
    a, b = (integrated_lufs(s.audio.samples, SR) for s in srcs.values())
    assert abs(a - b) < 1.0
    assert srcs["a"].lufs_target == srcs["b"].lufs_target == pytest.approx(srcs["a"].lufs_in, abs=0.01)


def test_loud_masters_are_capped_not_made_louder():
    srcs = {"a": loaded(-3), "b": loaded(-9)}   # both louder than the cap
    before = srcs["a"].lufs_in
    match_loudness(srcs)
    assert before > LUFS_CAP
    assert srcs["a"].lufs_target == LUFS_CAP
    assert integrated_lufs(srcs["a"].audio.samples, SR) <= before


def test_single_source_is_untouched():
    s = loaded(-30)
    orig = s.audio
    match_loudness({"a": s})
    assert s.audio is orig and s.lufs_target == s.lufs_in


def test_single_source_plan_loads_byte_identical(demo):
    root, tid = demo
    d = root / tid
    data = json.loads((tickets.iteration_dir(tid, 1, 2, root) / "plan.json").read_text())
    data["sources"] = {"a": data["sources"]["a"]}
    plan = Plan.model_validate(data)
    got = load_sources(plan, d)["a"].audio.samples
    assert np.array_equal(got, _load_audio(d / plan.sources["a"].file).samples)


def test_demo_medley_is_level_matched_and_reported(demo):
    root, tid = demo
    d = root / tid
    plan = Plan.model_validate_json((tickets.iteration_dir(tid, 1, 1, root) / "plan.json").read_text())
    src = load_sources(plan, d)
    la, lb = (integrated_lufs(src[k].audio.samples, src[k].audio.sr) for k in "ab")
    assert abs(la - lb) < 1.0
    _, info = render_plan(plan, d)
    a, b = info.sources["a"], info.sources["b"]
    assert a.lufs_in is not None and a.lufs_in - b.lufs_in == pytest.approx(6, abs=0.5)
    assert a.lufs_target == b.lufs_target <= LUFS_CAP
