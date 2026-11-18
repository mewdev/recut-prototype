"""The final-chord-hit recipe in skills/cutting/references/exit-design.md renders as documented.

Recipe from 20261118-idzo (4 rejected endings before a single chord hit + reverb bloom was
approved). The `ending_drums` regression is in tests/validator/test_linter_activity.py.
"""

import json
import re
from pathlib import Path

from recut.contracts import Plan
from recut.engine import render_plan

DOC = Path(__file__).resolve().parents[2] / "skills" / "cutting" / "references" / "exit-design.md"
HIT = next(json.loads(b) for b in re.findall(r"```json\n(.*?)```", DOC.read_text(), re.S) if '"id": "hit"' in b)


def _plan(hit: dict) -> Plan:
    return Plan.model_validate({
        "version": 2,
        "sources": {"a": {"file": "inputs/a.mp3", "map": "maps/a.json"}},
        "returns": [{"id": "A", "name": "Reverb", "devices": [
            {"id": "lc", "type": "eq", "low_cut": 250},
            {"id": "verb", "type": "reverb", "decay": "4s", "size": 55, "hi_cut": 5000, "dry_wet": 100}]}],
        "tracks": [{"id": "main", "clips": [
            {"id": "n1", "type": "clip", "source": "a", "segment": "verse", "index": 1},
            {"id": "n2", "type": "clip", "source": "a", "segment": "chorus", "index": 1},
            hit]}],
    })


def test_final_hit_recipe_rings_out_cleanly(demo):
    root, tid = demo
    _, info = render_plan(_plan(HIT), root / tid)
    assert info.returns_tail_end is not None and info.returns_tail_end > info.segments[-1].out_end + 1.0
    assert not [x for x in info.issues if x.severity == "error"], info.issues
    assert not [x for x in info.issues if x.rule in ("ending", "ending_drums", "qc_limiting")], info.issues

