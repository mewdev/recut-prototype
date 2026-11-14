"""`GET /api/tickets/{id}` carries the client feedback (C0)."""

from fastapi.testclient import TestClient

from recut import tickets
from recut.contracts import Review
from recut.server.app import create_app


def test_ticket_api_lists_client_feedback(tmp_path):
    root = tmp_path / "tickets"
    root.mkdir()
    tid = tickets.create_ticket("make it 30s", [], root=root)
    n = tickets.new_session(tid, agent="test", root=root)
    k = tickets.new_iteration(tid, n, {"version": 2}, root=root)
    tickets.save_review(tid, n, Review(iteration=k, verdict="ship"), root=root)
    c = TestClient(create_app(root))
    assert c.get(f"/api/tickets/{tid}").json()["client_feedback"] == []

    tickets.add_client_feedback(tid, "approved", rating=4, note="loved it", root=root)
    fb = c.get(f"/api/tickets/{tid}").json()["client_feedback"]
    assert len(fb) == 1
    assert (fb[0]["session"], fb[0]["iteration"], fb[0]["decision"], fb[0]["rating"], fb[0]["note"],
            fb[0]["channel"]) == (1, 1, "approved", 4, "loved it", "manual")
