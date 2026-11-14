"""L1: ticket-level timeline (events.jsonl) and per-session usage/cost (usage.json)."""

import json
import os

import pytest

from recut import sync, tickets, usage
from recut.contracts import Review


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "tickets"
    r.mkdir()
    return r


def test_events_written_by_each_action(root):
    tid = tickets.create_ticket("x", [], root=root)
    n = tickets.new_session(tid, agent="a", model="sonnet", root=root)
    k = tickets.new_iteration(tid, n, {"version": 2}, root=root)
    tickets.set_status(tid, "in_progress", root)  # no change: no event
    tickets.save_review(tid, n, Review(iteration=k, verdict="fixable"), root=root)
    k2 = tickets.new_iteration(tid, n, {"version": 2}, root=root)
    tickets.save_review(tid, n, Review(iteration=k2, verdict="ship"), root=root)
    tickets.add_client_feedback(tid, "approved", rating=5, root=root)
    evs = [json.loads(line) for line in (root / tid / "events.jsonl").read_text().splitlines()]
    ops = [e["op"] for e in evs]
    assert ops == ["created", "session_started", "status", "reviewed", "status", "reviewed",
                   "shipped", "status", "client_feedback", "status"]
    assert evs[1]["n"] == 1 and evs[1]["model"] == "sonnet"
    assert [(e["from"], e["to"]) for e in evs if e["op"] == "status"][0] == ("new", "in_progress")
    assert evs[-2]["decision"] == "approved" and evs[-2]["rating"] == 5
    assert not any(e.get("derived") for e in tickets.ticket_timeline(tid, root))


def test_render_events(demo):
    root, tid = demo
    before = [e for e in tickets.ticket_timeline(tid, root) if e["op"] == "rendered"]
    tickets.render_iteration(tid, 1, 1, root)
    after = [e for e in tickets.ticket_timeline(tid, root) if e["op"] == "rendered"]
    assert len(after) == len(before) + 1 and after[-1]["duration_s"] > 0


def test_derived_timeline_for_old_ticket(root):
    tid = tickets.create_ticket("x", [], root=root)
    n = tickets.new_session(tid, agent="a", model="m", root=root)
    k = tickets.new_iteration(tid, n, {"version": 2}, root=root)
    tickets.save_review(tid, n, Review(iteration=k, verdict="ship"), root=root)
    tickets.add_client_feedback(tid, "changes", root=root)
    (root / tid / "events.jsonl").unlink()  # a ticket from before L1
    tl = tickets.ticket_timeline(tid, root)
    assert [e["op"] for e in tl] == ["created", "session_started", "reviewed", "shipped", "client_feedback"]
    assert all(e["derived"] for e in tl)
    assert tl[1]["model"] == "m" and tl[3]["k"] == k


def test_real_events_suppress_derived(root):
    tid = tickets.create_ticket("x", [], root=root)
    tickets.new_session(tid, root=root)
    assert [e["op"] for e in tickets.ticket_timeline(tid, root)] == ["created", "session_started", "status"]


def _line(**kw):
    return json.dumps(kw)


def _transcript():
    def asst(mid, model, ts, i, o, cr=0, cw=0):
        return _line(type="assistant", timestamp=ts, message={
            "id": mid, "model": model, "usage": {
                "input_tokens": i, "output_tokens": o,
                "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw}})
    return "\n".join([
        _line(type="user", timestamp="2026-11-01T10:00:00Z", message={"role": "user", "content": "hi"}),
        "not json {{",
        _line(type="summary", leaf="x"),
        asst("m1", "claude-sonnet-5-5", "2026-11-01T10:00:10Z", 100, 5, 1000, 200),
        asst("m1", "claude-sonnet-5-5", "2026-11-01T10:00:11Z", 100, 50, 1000, 200),  # dup: last wins
        _line(type="user", timestamp="2026-11-01T10:01:00Z", message={
            "role": "user", "content": [{"type": "tool_result", "content": "ok"}]}),  # not a prompt
        asst("m2", "claude-opus-4-1", "2026-11-01T10:02:00Z", 10, 20),
        _line(type="user", timestamp="2026-11-01T10:05:00Z", message={
            "role": "user", "content": [{"type": "text", "text": "more"}]}),
    ])


def test_usage_parsing_two_models_dupes_junk():
    u = usage.parse_transcript(_transcript())
    assert u["input_tokens"] == 110 and u["output_tokens"] == 70
    assert u["cache_read_tokens"] == 1000 and u["cache_write_tokens"] == 200
    assert u["turns"] == 2 and u["duration_s"] == 300.0
    assert u["model"] == "claude-sonnet-5-5"
    assert set(u["models"]) == {"claude-sonnet-5-5", "claude-opus-4-1"}
    expected = (100 * 3 + 50 * 15 + 1000 * 0.3 + 200 * 3.75) / 1e6 + (10 * 5 + 20 * 25) / 1e6
    assert u["cost_usd"] == pytest.approx(expected, abs=1e-4)


def test_cost_math_and_unknown_model():
    assert usage.cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000, 1_000_000, 1_000_000) == pytest.approx(
        1 + 5 + 0.1 + 1.25)
    assert usage.cost_usd("mystery-model", 1, 1) is None
    t = _line(type="assistant", timestamp="2026-11-01T10:00:00Z",
              message={"id": "a", "model": "mystery", "usage": {"input_tokens": 5, "output_tokens": 5}})
    u = usage.parse_transcript(t)
    assert u["cost_usd"] is None and u["output_tokens"] == 5


def test_empty_transcript():
    u = usage.parse_transcript("")
    assert u["model"] is None and u["cost_usd"] is None and u["turns"] == 0 and u["duration_s"] == 0.0


def test_sync_computes_stale_usage(root):
    tid = tickets.create_ticket("x", [], root=root)
    n = tickets.new_session(tid, root=root)
    sd = tickets.session_dir(tid, n, root)
    assert usage.load_usage(sd) is None
    (sd / "transcript.jsonl").write_text(_transcript())
    sync.sync(root)
    first = usage.load_usage(sd)
    assert first and first["turns"] == 2
    # a transcript copied later (newer mtime) is picked up; an unchanged one is not recomputed
    (sd / "transcript.jsonl").write_text(_transcript() + "\n" + _line(
        type="user", timestamp="2026-11-01T10:06:00Z", message={"role": "user", "content": "again"}))
    t = (sd / "usage.json").stat().st_mtime
    os.utime(sd / "usage.json", (t - 20, t - 20))
    assert usage.refresh_stale(root) == [sd]
    assert usage.load_usage(sd)["turns"] == 3
    assert usage.refresh_stale(root) == []


def test_api_exposes_timeline_and_usage(demo):
    from fastapi.testclient import TestClient

    from recut.server.app import create_app

    root, tid = demo
    t = TestClient(create_app(root)).get(f"/api/tickets/{tid}").json()
    assert t["timeline"][0]["op"] == "created"
    assert "usage" in t["sessions"][0]
