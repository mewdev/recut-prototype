"""The three ending-transplant plan snippets in skills/cutting/references/ending-transplant.md render."""

import json
import re
from pathlib import Path

import pytest

from recut.contracts import Plan
from recut.engine import render_plan

DOC = Path(__file__).resolve().parents[2] / "skills" / "cutting" / "references" / "ending-transplant.md"
SNIPPETS = [json.loads(b) for b in re.findall(r"```json\n(.*?)```", DOC.read_text(), re.S) if '"tracks"' in b]
SOURCES = {"a": {"file": "inputs/a.mp3", "map": "maps/a.json"}}


def test_the_doc_has_three_variants():
    assert len(SNIPPETS) == 3


@pytest.mark.parametrize("i", [0, 1, 2])
def test_variant_renders_with_a_ringing_tail_and_no_errors(demo, i):
    root, tid = demo
    plan = Plan.model_validate({"version": 2, "sources": SOURCES, **SNIPPETS[i]})
    audio, info = render_plan(plan, root / tid)
    assert info.returns_tail_end is not None and info.returns_tail_end > info.segments[-1].out_start
    assert not [x for x in info.issues if x.severity == "error"], info.issues
    assert not [x for x in info.issues if x.rule == "not_rendered"]
    assert info.splices[-1].overlap_ms > 0


@pytest.mark.parametrize("i", [0, 1, 2])
def test_variant_does_not_squash_the_limiter_on_a_loud_master(demo, i):
    """Regression (ticket 20261113-mbyv): a full-range return reverb with a send ramped to 0 dB
    pumped the master limiter on a loud mastered source (3.4 dB, `fx_wrong`). The documented
    recipes (return low cut, moderate decay, send peak -9 to -13 dB) must stay under 3 dB."""
    root, tid = demo
    plan = Plan.model_validate({"version": 2, "sources": SOURCES, **SNIPPETS[i]})
    _, info = render_plan(plan, root / tid)
    assert not [x for x in info.issues if x.rule == "qc_limiting"], info.issues
    assert info.qc["max_gain_reduction_db"] <= 3.0, info.qc
    # a loud master is not a defect: loudness and true peak are judged against the source / the ceiling
    assert not [x for x in info.issues if x.rule in ("qc_loudness", "qc_true_peak")], info.issues


def test_the_doc_follows_the_return_recipe():
    for s in SNIPPETS:
        assert s["returns"][0]["devices"][0].get("low_cut", 0) >= 200
        for t in s["tracks"]:
            for c in t["clips"]:
                for a in c.get("automation", []):
                    if str(a["target"]).startswith("sends."):
                        assert a.get("from") not in ("-inf", None), a
                        assert -13 <= a["to"] <= -9, a
                        assert a["over"] in ("2 beats", "1 bar", "2 bars"), a
                for v in (c.get("sends") or {}).values():
                    assert v != "-inf" and v <= -9, c


def test_the_old_wash_is_what_limited_hard(demo):
    """The test above is not vacuous: the pre-recipe wash (no low cut, 3.5 s, -inf to 0 dB) limits harder."""
    root, tid = demo
    s = json.loads(json.dumps(SNIPPETS[1]))
    s["returns"][0]["devices"] = [
        {"id": "verb", "type": "reverb", "decay": "3.5s", "pre_delay": "20ms", "size": 80, "hi_cut": 6000, "dry_wet": 100}
    ]
    clip = s["tracks"][0]["clips"][1]
    clip["sends"] = {"A": "-inf"}
    clip["automation"] = [{"target": "sends.A", "from": "-inf", "to": 0, "over": "1 beat", "at": "end", "shape": "exp"}]
    _, old = render_plan(Plan.model_validate({"version": 2, "sources": SOURCES, **s}), root / tid)
    _, new = render_plan(Plan.model_validate({"version": 2, "sources": SOURCES, **SNIPPETS[1]}), root / tid)
    assert old.qc["max_gain_reduction_db"] > new.qc["max_gain_reduction_db"] + 0.5
