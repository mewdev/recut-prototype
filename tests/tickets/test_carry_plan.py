"""Reworking a ticket keeps the cut: a copied plan renders where its previous render put each
clip, even when the code now counts bars differently (nominal tempo -> the map's downbeats)."""

import json

import pytest

from recut import tickets
from recut.contracts import ClipNode
from recut.engine import _clip_bounds
from recut.map.parser import parse_recut_map


@pytest.fixture
def rendered(tmp_path):
    """Demo ticket whose latest plan has a clip placed in bars, rendered."""
    root = tmp_path / "tickets"
    tid = tickets.create_demo_ticket(root=root)
    n, k = tickets._latest_plan_at(tid, root)
    d = tickets.iteration_dir(tid, n, k, root)
    plan = json.loads((d / "plan.json").read_text())
    clip = next(c for c in plan["tracks"][0]["clips"] if c["type"] == "clip")
    clip.update(offset_bars=1, bars=2)
    (d / "plan.json").write_text(json.dumps(plan))
    tickets.render_iteration(tid, n, k, root)
    return root, tid, d, clip["id"]


def _old_render(d, cid, shift_s):
    """Pretend the render was made by code that counted bars differently: the clip sat elsewhere."""
    r = json.loads((d / "render.json").read_text())
    seg = next(s for s in r["segments"] if s["node_id"] == cid)
    seg["src_start"] += shift_s
    seg["src_end"] += shift_s
    (d / "render.json").write_text(json.dumps(r))
    return seg["src_start"], seg["src_end"]


def _bounds(root, tid, plan, cid):
    c = next(c for t in plan["tracks"] for c in t["clips"] if c.get("id") == cid)
    m = parse_recut_map(tickets.ticket_dir(tid, root) / plan["sources"][c["source"]]["map"])
    return _clip_bounds(ClipNode.model_validate(c), m)


def test_copy_lands_where_the_previous_render_put_the_clip(rendered):
    root, tid, d, cid = rendered
    want = _old_render(d, cid, 0.3)
    plan, notes = tickets.carry_plan(tid, root)
    assert _bounds(root, tid, plan, cid) == (pytest.approx(want[0], abs=5e-4), pytest.approx(want[1], abs=5e-4))
    assert notes and cid in notes[0] and "300 ms" in notes[0]
    # new_iteration's default copy is the same carried plan
    k = tickets.new_iteration(tid, 1, root=root)
    assert json.loads((tickets.iteration_dir(tid, 1, k, root) / "plan.json").read_text()) == plan


def test_unchanged_when_the_render_matches(rendered):
    root, tid, d, _ = rendered
    plan, notes = tickets.carry_plan(tid, root)
    assert notes == [] and plan == json.loads((d / "plan.json").read_text())


def test_stale_render_is_not_used(rendered):
    root, tid, d, cid = rendered
    _old_render(d, cid, 0.3)
    (d / "plan.json").write_text((d / "plan.json").read_text())  # plan edited after the render
    plan, notes = tickets.carry_plan(tid, root)
    assert notes == [] and plan == json.loads((d / "plan.json").read_text())


def test_rework_starts_from_the_shipped_plan_not_a_later_one(rendered):
    from recut.contracts import Review

    root, tid, d, cid = rendered
    n, k = tickets._latest_plan_at(tid, root)
    tickets.save_review(tid, n, Review(iteration=k, verdict="ship"), root=root)
    shipped = json.loads((d / "plan.json").read_text())
    later = tickets.new_iteration(tid, n, root=root)  # an unreviewed try after the ship
    p = tickets.iteration_dir(tid, n, later, root) / "plan.json"
    p.write_text(json.dumps({**shipped, "notes": "experiment"}))

    plan, notes = tickets.carry_plan(tid, root, from_shipped=True)
    assert plan == shipped and f"it{k}" in notes[0] and f"it{later}" in notes[0]
    assert tickets.carry_plan(tid, root)[0]["notes"] == "experiment"  # iterate: latest plan
