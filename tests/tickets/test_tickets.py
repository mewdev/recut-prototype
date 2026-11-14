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


def test_each_iteration_keeps_its_review(demo):
    root, tid = demo
    tickets.save_review(tid, 1, Review(iteration=1, verdict="reject", tags=["abrupt"]), root)
    tickets.save_review(tid, 1, Review(iteration=2, verdict="fixable"), root)
    assert tickets.load_iteration_review(tid, 1, 1, root).verdict == "reject"
    assert tickets.load_iteration_review(tid, 1, 2, root).verdict == "fixable"
    assert tickets.load_review(tid, 1, root).iteration == 2  # session copy = latest


def test_awaiting_client_feedback(tmp_path, demo):
    import time

    droot, dtid = demo
    audio = droot / dtid / "inputs" / "a.mp3"
    tid = tickets.create_ticket("real client", [("song.mp3", audio)], 30, root=tmp_path)
    n = tickets.new_session(tid, agent="claude-code", model="sonnet", root=tmp_path)
    k = tickets.new_iteration(tid, n, {"version": 2}, root=tmp_path)
    assert tickets.awaiting_client(tmp_path) == []  # not shipped yet

    tickets.save_review(tid, n, Review(iteration=k, verdict="ship"), tmp_path)
    waiting = tickets.awaiting_client(tmp_path)
    assert [w["id"] for w in waiting] == [tid] and (waiting[0]["session"], waiting[0]["iteration"]) == (n, k)
    assert f"recut ticket client {tid}" in tickets.awaiting_client_message(tmp_path)

    time.sleep(1.1)  # timestamps have 1 s resolution
    tickets.add_client_feedback(tid, "approved", rating=5, root=tmp_path)
    assert tickets.awaiting_client(tmp_path) == []
    assert tickets.awaiting_client_message(tmp_path) == ""

    time.sleep(1.1)  # a later re-ship waits for a new reaction
    k2 = tickets.new_iteration(tid, n, root=tmp_path)
    tickets.save_review(tid, n, Review(iteration=k2, verdict="ship"), tmp_path)
    assert [w["iteration"] for w in tickets.awaiting_client(tmp_path)] == [k2]


def test_demo_tickets_never_await_client(demo):
    root, tid = demo
    tickets.save_review(tid, 1, Review(iteration=2, verdict="ship"), root)
    assert tid not in [w["id"] for w in tickets.awaiting_client(root)]
