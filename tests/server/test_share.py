"""B5+: client share page, public audio routes, decisions."""

import json
import shutil

import pytest
from fastapi.testclient import TestClient

from recut import tickets
from recut.contracts import Review
from recut.server.app import create_app


@pytest.fixture()
def env(demo, tmp_path):
    root0, tid = demo
    root = tmp_path / "tickets"
    shutil.copytree(root0, root)
    for f in (root / tid).rglob("review.json"):  # start with no reviews
        f.unlink()
    return root, tid, TestClient(create_app(root))


def ship(root, tid, k=2, verdict="ship"):
    tickets.save_review(tid, 1, Review(iteration=k, verdict=verdict), root=root)


def test_share_409_unless_ship(env):
    root, tid, c = env
    assert c.post(f"/api/tickets/{tid}/share").status_code == 409
    ship(root, tid, 2, "fixable")
    assert c.post(f"/api/tickets/{tid}/share").status_code == 409
    assert c.post(f"/api/tickets/{tid}/share", json={"session": 1, "iteration": 2}).status_code == 409


def test_share_ok_reuse_and_new_token(env):
    root, tid, c = env
    ship(root, tid, 1)
    r = c.post(f"/api/tickets/{tid}/share").json()
    assert r["url"].endswith("/s/" + r["token"])
    assert json.loads((root / tid / "share.json").read_text())["iteration"] == 1
    assert c.post(f"/api/tickets/{tid}/share").json()["token"] == r["token"]
    ship(root, tid, 2)
    r2 = c.post(f"/api/tickets/{tid}/share").json()
    assert r2["token"] != r["token"]
    assert c.get(f"/s/{r['token']}").status_code == 404  # old link replaced
    assert c.get(f"/api/tickets/{tid}").json()["share"]["token"] == r2["token"]


def test_public_page_is_ticket_neutral_and_audio_ranges(env):
    root, tid, c = env
    ship(root, tid)
    tok = c.post(f"/api/tickets/{tid}/share").json()["token"]
    page = c.get(f"/s/{tok}")
    assert page.status_code == 200
    for bad in (tid, "/media/", "inputs/", "sessions/", ".wav"):
        assert bad not in page.text
    assert "may be used, anonymised, to improve the service" in page.text
    for which in ("cut", "original"):
        r = c.get(f"/s/{tok}/audio/{which}", headers={"Range": "bytes=0-99"})
        assert r.status_code == 206 and len(r.content) == 100


def test_decision_records_feedback_and_multiple_rounds(env):
    root, tid, c = env
    ship(root, tid)
    tok = c.post(f"/api/tickets/{tid}/share").json()["token"]
    body = {"approved": False, "rating": 2, "note": "too long"}
    assert c.post(f"/api/share/{tok}/decision", json=body).status_code == 200
    assert c.post(f"/api/share/{tok}/decision", json={"approved": True, "rating": 5}).status_code == 200
    fb = tickets.load_client_feedback(tid, root)
    assert [(f.decision, f.rating, f.channel, f.session, f.iteration) for f in fb] == [
        ("changes", 2, "share_page", 1, 2), ("approved", 5, "share_page", 1, 2)]
    assert tickets.load_request(tid, root).status == "client_approved"
    sh = json.loads((root / tid / "share.json").read_text())
    assert sh["client_decision"] == "approved" and sh["client_note"] is None
    assert tid not in {a["id"] for a in tickets.awaiting_client(root)}
    assert c.post(f"/api/share/{tok}/decision", json={"approved": True, "rating": 9}).status_code == 422


def test_unknown_token_404(env):
    _, _, c = env
    assert c.get("/s/nope").status_code == 404
    assert c.get("/s/nope/audio/cut").status_code == 404
    assert c.get("/s/nope/audio/original").status_code == 404
    assert c.post("/api/share/nope/decision", json={"approved": True}).status_code == 404
