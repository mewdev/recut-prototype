import json

from recut import tickets
from recut.contracts import Review


def test_ticket_lifecycle(tmp_path, demo):
    droot, dtid = demo
    audio = droot / dtid / "inputs" / "a.mp3"
    tid = tickets.create_ticket("make it 30s", [("song.mp3", audio)], 30, root=tmp_path)
    assert tickets.load_request(tid, tmp_path).files == {"a": "song.mp3"}
    assert tickets.sources(tid, tmp_path)["a"]["map"] is None

    mapped = tickets.ensure_maps(tid, tmp_path, analyze=lambda p: _demo_map(droot, dtid))
    assert mapped == ["a"] and tickets.sources(tid, tmp_path)["a"]["map"] == "maps/a.json"

    n = tickets.new_session(tid, agent="test", model="haiku", root=tmp_path)
    plan = json.loads((tickets.iteration_dir(dtid, 1, 1, droot) / "plan.json").read_text())
    plan["sources"] = {"a": plan["sources"]["a"]}
    for c in plan["tracks"][0]["clips"]:
        if c.get("source") == "b":
            c["source"] = "a"
    k = tickets.new_iteration(tid, n, plan, root=tmp_path)
    assert tickets.is_stale(tid, n, k, tmp_path)
    assert tickets.render_stale(tid, tmp_path) == [(n, k)]
    assert not tickets.is_stale(tid, n, k, tmp_path)
    assert tickets.load_request(tid, tmp_path).status == "in_review"

    k2 = tickets.new_iteration(tid, n, root=tmp_path)  # copies previous plan
    assert (tickets.iteration_dir(tid, n, k2, tmp_path) / "plan.json").read_text() == \
        (tickets.iteration_dir(tid, n, k, tmp_path) / "plan.json").read_text()

    tickets.save_review(tid, n, Review(iteration=k, verdict="fixable", tags=["abrupt"]), tmp_path)
    assert tickets.load_request(tid, tmp_path).status == "needs_rework"
    events = [json.loads(line) for line in (tickets.session_dir(tid, n, tmp_path) / "events.jsonl").read_text().splitlines()]
    assert [e["op"] for e in events] == ["render", "review"]


def test_render_error_written_and_cleared(demo, tmp_path):
    droot, dtid = demo
    d = tickets.iteration_dir(dtid, 1, 1, droot)
    good = (d / "plan.json").read_text()
    bad = json.loads(good)
    bad["tracks"][0]["clips"][0]["segment"] = "outro"
    (d / "plan.json").write_text(json.dumps(bad))
    out = tickets.render_iteration(dtid, 1, 1, droot)
    assert "outro" in out["error"] and (d / "render_error.json").exists() and not (d / "render.json").exists()
    (d / "plan.json").write_text(good)
    tickets.render_iteration(dtid, 1, 1, droot)
    assert (d / "render.json").exists() and not (d / "render_error.json").exists()


def _demo_map(root, tid):
    from recut.map.parser import parse_recut_map
    return parse_recut_map(root / tid / "maps" / "a.json")
