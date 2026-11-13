"""A9: musical linter rules (phrase_align, ending, energy_drop, duration), one pass + one fail each."""

import copy
import json

import pytest

from recut import tickets
from recut.contracts import Plan
from recut.engine import render_plan

LINT = {"phrase_align", "ending", "energy_drop", "duration"}


@pytest.fixture
def base(demo):
    root, tid = demo
    return root / tid, json.loads((tickets.iteration_dir(tid, 1, 2, root) / "plan.json").read_text())


def clip(i, seg, idx=1, **kw):
    return {"id": i, "type": "clip", "source": "a", "segment": seg, "index": idx, **kw}


def lint(base, clips, **extra):
    d, p = base
    p = copy.deepcopy(p)
    p["tracks"][0]["clips"] = clips
    p.pop("target_duration_s", None)
    p.update(extra)
    _, info = render_plan(Plan.model_validate(p), d)
    return [i for i in info.issues if i.rule in LINT]


def rules(issues):
    return {i.rule for i in issues}


END = {"offset_bars": 4}  # last 4 bars of the 9-bar inst, ending at the section end


def test_phrase_align_passes_on_phrase_boundaries(base):
    out = lint(base, [clip("n1", "verse", bars=4), clip("n2", "chorus", bars=4), clip("n3", "inst", **END)])
    assert "phrase_align" not in rules(out)


def test_phrase_align_flags_incoming_and_outgoing(base):
    out = lint(base, [clip("n1", "verse", bars=3), clip("n2", "chorus", offset_beats=1, bars=2),
                      clip("n3", "inst", **END)])
    pa = [i for i in out if i.rule == "phrase_align"]
    assert {i.splice for i in pa} == {"s1", "s2"} and all(i.severity == "warn" for i in pa)
    assert any("outgoing" in i.message for i in pa) and any("incoming" in i.message for i in pa)
    assert pa[0].node == "n2"


def test_ending_passes_at_section_end_or_with_fade(base):
    assert "ending" not in rules(lint(base, [clip("n1", "verse"), clip("n2", "inst", **END)]))
    faded = [clip("n1", "verse"), clip("n2", "chorus", bars=4, fade_out={"length": "1 bar", "shape": "exp"})]
    assert "ending" not in rules(lint(base, faded))


def test_ending_flags_a_mid_section_stop(base):
    out = lint(base, [clip("n1", "verse"), clip("n2", "chorus", bars=4)])
    e = [i for i in out if i.rule == "ending"]
    assert len(e) == 1 and e[0].node == "n2" and e[0].severity == "warn"


def test_energy_drop_flags_loud_to_quiet_hard_cut(base):
    # chorus ends at -9.9 dB, the next chorus clip is 8 dB quieter
    clips = [clip("n1", "chorus"), clip("n2", "chorus", gain=-8, bars=4)]
    out = [i for i in lint(base, clips) if i.rule == "energy_drop"]
    assert len(out) == 1 and out[0].splice == "s1" and out[0].node == "n2"


def test_energy_drop_quiet_when_level_holds_or_the_join_is_smoothed(base):
    assert "energy_drop" not in rules(lint(base, [clip("n1", "chorus"), clip("n2", "chorus", bars=4)]))
    smoothed = [clip("n1", "chorus"), {"id": "x", "type": "xfade", "length": "1 beat"},
                clip("n2", "chorus", gain=-8, bars=4)]
    assert "energy_drop" not in rules(lint(base, smoothed))
    faded = [clip("n1", "chorus", fade_out={"length": "1 beat", "shape": "linear"}),
             clip("n2", "chorus", gain=-8, bars=4)]
    assert "energy_drop" not in rules(lint(base, faded))


def test_duration_ok_warn_and_error(base):
    clips = [clip("n1", "intro"), clip("n2", "verse"), clip("n3", "chorus")]  # ~46.4 s
    assert "duration" not in rules(lint(base, clips, target_duration_s=46))
    warn = [i for i in lint(base, clips, target_duration_s=50) if i.rule == "duration"]
    assert [i.severity for i in warn] == ["warn"]
    err = [i for i in lint(base, clips, target_duration_s=55) if i.rule == "duration"]
    assert [i.severity for i in err] == ["error"]


def test_duration_reported_once(base):
    out = lint(base, [clip("n1", "verse")], target_duration_s=60)
    assert [i.rule for i in out].count("duration") == 1
