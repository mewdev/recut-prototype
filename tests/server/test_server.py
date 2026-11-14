import pytest
from fastapi.testclient import TestClient

from recut.server.app import create_app


@pytest.fixture
def client(demo):
    root, tid = demo
    return TestClient(create_app(root)), tid


def test_pages_and_list(client):
    c, tid = client
    assert "Recut" in c.get("/").text and "Recut" in c.get(f"/t/{tid}").text
    assert [t["id"] for t in c.get("/api/tickets").json()] == [tid]


def test_ticket_and_iteration(client):
    c, tid = client
    t = c.get(f"/api/tickets/{tid}").json()
    assert [i["k"] for i in t["sessions"][0]["iterations"]] == [1, 2]
    it = c.get(f"/api/tickets/{tid}/sessions/1/iterations/2").json()
    assert it["render"]["splices"][2]["out_shape"] == "hold" and it["audio_version"]


def test_map_is_strict_json(client):
    c, tid = client
    r = c.get(f"/api/tickets/{tid}/maps/a")
    assert r.status_code == 200 and "NaN" not in r.text


def test_media_range_and_traversal(client):
    c, tid = client
    r = c.get(f"/media/tickets/{tid}/inputs/a.mp3", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    assert c.get(f"/media/tickets/{tid}/../../etc/passwd").status_code == 404


def test_review_roundtrip_sets_status(client):
    c, tid = client
    body = {"iteration": 2, "verdict": "ship", "splices": {"s3": {"ok": True}}}
    assert c.put(f"/api/tickets/{tid}/sessions/1/review", json=body).json()["status"] == "in_review"
    assert c.put(f"/api/tickets/{tid}/sessions/1/review", json={**body, "verdict": "nope"}).status_code == 422


def test_upload_creates_ticket(client, tmp_path):
    c, tid = client
    r = c.post("/api/tickets", data={"text": "shorter please", "target_duration_s": "60", "override": "true"},  # fake bytes: intake blocks
               files=[("files", ("x.mp3", b"ID3fake", "audio/mpeg"))])
    new = r.json()["id"]
    assert c.get(f"/api/tickets/{new}").json()["request"]["files"] == {"a": "x.mp3"}
