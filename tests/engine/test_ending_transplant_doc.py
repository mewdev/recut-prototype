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
