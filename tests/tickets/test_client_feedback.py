"""Manual client feedback (C0): `add_client_feedback` / `load_client_feedback` on a hand-built ticket store."""

import json

import pytest
from pydantic import ValidationError

from recut import tickets
from recut.contracts import Review


@pytest.fixture
def root(tmp_path):
    return tmp_path / "tickets"


def _ticket(root, verdicts, session_verdicts=None):
    """One session per list in `session_verdicts` (default: one session with `verdicts`).
    A verdict of None means an iteration with no review."""
    root.mkdir(exist_ok=True)
    tid = tickets.create_ticket("make it 30s", [], root=root)
    for group in session_verdicts or [verdicts]:
        n = tickets.new_session(tid, agent="test", model="m", root=root)
        for v in group:
            k = tickets.new_iteration(tid, n, {"version": 2}, root=root)
            if v is not None:
                tickets.save_review(tid, n, Review(iteration=k, verdict=v), root=root)
    return tid


def _events(tid, n, root):
    p = tickets.session_dir(tid, n, root) / "events.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()]


def test_defaults_to_latest_shipped_iteration(root):
    tid = _ticket(root, ["fixable", "ship", None])  # it2 is the shipped one, it3 came after
    fb = tickets.add_client_feedback(tid, "approved", rating=4, note="  loved it ", root=root)
    assert (fb.session, fb.iteration, fb.decision, fb.rating, fb.note, fb.channel) == \
        (1, 2, "approved", 4, "loved it", "manual")
    assert tickets.load_request(tid, root).status == "client_approved"
    ev = [e for e in _events(tid, 1, root) if e["op"] == "client_feedback"]
    assert len(ev) == 1 and ev[0]["iteration"] == 2 and ev[0]["decision"] == "approved" and ev[0]["rating"] == 4


def test_shipped_in_an_earlier_session_still_wins_over_later_unshipped(root):
    tid = _ticket(root, None, session_verdicts=[["ship"], ["fixable", None]])
    fb = tickets.add_client_feedback(tid, "approved", root=root)
    assert (fb.session, fb.iteration) == (1, 1)


def test_without_a_ship_review_attaches_to_the_latest_iteration(root):
    tid = _ticket(root, ["fixable", None])
    fb = tickets.add_client_feedback(tid, "changes", note="too long", root=root)
    assert (fb.session, fb.iteration, fb.rating, fb.note) == (1, 2, None, "too long")
    assert tickets.load_request(tid, root).status == "client_changes"


def test_rounds_are_appended_in_order_and_status_follows_the_last(root):
    tid = _ticket(root, ["fixable", "ship"])
    tickets.add_client_feedback(tid, "changes", rating=2, note="too long", iteration=1, root=root)
    assert tickets.load_request(tid, root).status == "client_changes"
    tickets.add_client_feedback(tid, "approved", rating=5, root=root)

    fbs = tickets.load_client_feedback(tid, root)
    assert [(f.iteration, f.decision, f.rating) for f in fbs] == [(1, "changes", 2), (2, "approved", 5)]
    lines = (tickets.ticket_dir(tid, root) / "client_feedback.jsonl").read_text().splitlines()
    assert len(lines) == 2  # append-only: one JSON line per reaction
    assert tickets.load_request(tid, root).status == "client_approved"
    assert [e["op"] for e in _events(tid, 1, root)].count("client_feedback") == 2


def test_explicit_session_and_iteration(root):
    tid = _ticket(root, None, session_verdicts=[["ship", "ship"], [None, "fixable", None]])
    # bare iteration: the latest session that has it
    assert tickets.add_client_feedback(tid, "changes", iteration=2, root=root).session == 2
    # bare session: that session's shipped iteration, else its latest
    fb = tickets.add_client_feedback(tid, "approved", session=1, root=root)
    assert (fb.session, fb.iteration) == (1, 2)
    fb = tickets.add_client_feedback(tid, "changes", session=2, root=root)
    assert (fb.session, fb.iteration) == (2, 3)
    # both given, even when another iteration is shipped
    fb = tickets.add_client_feedback(tid, "approved", session=1, iteration=1, root=root)
    assert (fb.session, fb.iteration) == (1, 1)


def test_invalid_targets_and_values_are_refused(root):
    tid = _ticket(root, ["ship"])
    with pytest.raises(ValueError, match="no iteration 9"):
        tickets.add_client_feedback(tid, "approved", iteration=9, root=root)
    with pytest.raises(ValueError, match="no session 5"):
        tickets.add_client_feedback(tid, "approved", session=5, root=root)
    with pytest.raises(ValueError, match="no iteration 4 in session 1"):
        tickets.add_client_feedback(tid, "approved", session=1, iteration=4, root=root)
    with pytest.raises(ValidationError):
        tickets.add_client_feedback(tid, "approved", rating=6, root=root)
    with pytest.raises(ValidationError):
        tickets.add_client_feedback(tid, "maybe", root=root)
    empty = _ticket(root, [])
    with pytest.raises(ValueError, match="no iterations yet"):
        tickets.add_client_feedback(empty, "approved", root=root)
    assert tickets.load_client_feedback(tid, root) == []  # nothing written by the refused calls


def test_blank_note_is_none_and_missing_file_is_empty(root):
    tid = _ticket(root, ["ship"])
    assert tickets.load_client_feedback(tid, root) == []
    assert tickets.add_client_feedback(tid, "approved", note="   ", root=root).note is None
