"""M3: linter rules that read instrument activity (ending_drums, mid_vocal). No audio, no Modal."""

import copy
import json
import shutil

import pytest

from recut import tickets
from recut.contracts import Plan
from recut.engine import render_plan
from recut.map.activity import apply_activity
from recut.map.parser import parse_recut_map

RULES = {"ending_drums", "mid_vocal"}
N = 679  # 67.8 s at 100 ms


@pytest.fixture
def ticket(demo, tmp_path):
    root, tid = demo
    d = tmp_path / tid
    shutil.copytree(root / tid, d)
    plan = json.loads((tickets.iteration_dir(tid, 1, 2, root) / "plan.json").read_text())
    return d, plan


def set_activity(d, drums=None, vocal_span=None):
    """Write curves into the ticket's map: constant drums, vocals 1.0 inside `vocal_span`."""
    p = d / "maps" / "a.json"
    m = parse_recut_map(p)
    curves = {"drums": [drums] * N if drums is not None else [0.0] * N, "bass": [0.0] * N,
              "other": [0.0] * N, "vocals": [0.0] * N}
    if vocal_span:
        a, b = vocal_span
        curves["vocals"] = [1.0 if a <= i * 0.1 < b else 0.0 for i in range(N)]
    p.write_text(json.dumps(apply_activity(m, curves).model_dump()))


def lint(ticket, clips):
    d, plan = ticket
    plan = copy.deepcopy(plan)
    plan["tracks"][0]["clips"] = clips
    plan.pop("target_duration_s", None)
    _, info = render_plan(Plan.model_validate(plan), d)
    return [i for i in info.issues if i.rule in RULES]


def clip(i, seg, idx=1, **kw):
    return {"id": i, "type": "clip", "source": "a", "segment": seg, "index": idx, **kw}


FADE = {"length": "1 bar", "shape": "exp"}


def test_ending_drums_warns_on_a_fade_over_busy_drums(ticket):
    set_activity(ticket[0], drums=0.9)
    out = lint(ticket, [clip("n1", "verse"), clip("n2", "chorus", bars=4, fade_out=FADE)])
    assert [(i.rule, i.severity, i.node) for i in out] == [("ending_drums", "warn", "n2")]


def test_ending_drums_quiet_when_drums_are_sparse_or_there_is_no_fade(ticket):
    set_activity(ticket[0], drums=0.2)
    assert not lint(ticket, [clip("n1", "verse"), clip("n2", "chorus", bars=4, fade_out=FADE)])
    set_activity(ticket[0], drums=0.9)
    assert not lint(ticket, [clip("n1", "verse"), clip("n2", "inst", offset_bars=4)])  # no fade_out


def test_mid_vocal_flags_a_splice_inside_a_sung_phrase(ticket):
    set_activity(ticket[0], vocal_span=(31.86, 47.34))  # the chorus is sung
    out = lint(ticket, [clip("n1", "chorus", bars=4), clip("n2", "verse")])  # cut 4 bars into it
    assert [(i.rule, i.severity, i.splice) for i in out] == [("mid_vocal", "warn", "s1")]
    assert "outgoing" in out[0].message


def test_mid_vocal_quiet_at_range_edges_and_without_vocals(ticket):
    set_activity(ticket[0], vocal_span=(31.86, 47.34))
    # verse -> chorus joins at the range's start, chorus -> inst leaves at its end
    assert not lint(ticket, [clip("n1", "verse"), clip("n2", "chorus"), clip("n3", "inst", offset_bars=4)])
    set_activity(ticket[0], vocal_span=None)
    assert not lint(ticket, [clip("n1", "chorus", bars=4), clip("n2", "verse")])


def test_rules_skip_silently_when_the_map_has_no_activity(ticket):
    assert not lint(ticket, [clip("n1", "chorus", bars=4, fade_out=FADE), clip("n2", "verse")])


def test_ending_drums_ignores_a_click_cover_on_a_final_hit(ticket):
    """Regression 20261118-idzo: a one-beat final chord hit with a 30 ms anti-click fade drew
    `ending_drums` on every iteration (it5-it9, the shipped one too). That is not a fade-out."""
    set_activity(ticket[0], drums=0.9)
    hit = clip("n2", "chorus", beats=1, fade_out={"length": "30ms", "shape": "linear"})
    assert not lint(ticket, [clip("n1", "verse"), hit])
    hit["fade_out"] = {"length": "100ms", "shape": "linear"}  # from 100 ms on it is a fade
    assert [i.rule for i in lint(ticket, [clip("n1", "verse"), hit])] == ["ending_drums"]
