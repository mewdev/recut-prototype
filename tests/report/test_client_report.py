"""`recut report` "Client feedback" section (C0). Expected values are worked out by hand from the scenario:

  A  fixable (it1), ship (it2). Client: changes "too long" ★2 on it1, then approved ★4 on it2 (default).
  B  ship (it1). Client: approved ★5.
  C  reject (it1). Client: changes "wrong approach" ★1 (default = latest iteration, no ship).
  D  ship (it1). Client: changes "wrong ending" (operator said ship: disagreement).
  F  no review (it1). Client: changes "wrong crop", then approved ★3 (both unreviewed).
  G  ship (it1), no client feedback: ignored.

Tickets with feedback: 5. Last reaction approved: A, B, F = 3 (60 %). Rounds until approval: A 1, B 0, F 1 (median 1).
Never approved: C, D. Rated reactions: 2, 4, 5, 1, 3 (average 3.0). Reactions: 7.
Agreement over reactions with a review: 5 compared, 4 matched (D is the miss), 2 unreviewed (F).
"""

import json
import sys
from datetime import date

import pytest

from recut import report, tickets
from recut.cli import main
from recut.contracts import Review


def _ticket(root, verdicts):
    tid = tickets.create_ticket("make it 30s", [], root=root)
    n = tickets.new_session(tid, agent="test", model="m", root=root)
    for v in verdicts:
        k = tickets.new_iteration(tid, n, {"version": 2}, root=root)
        if v is not None:
            tickets.save_review(tid, n, Review(iteration=k, verdict=v), root=root)
    return tid


@pytest.fixture
def scen(tmp_path):
    root = tmp_path / "tickets"
    root.mkdir()
    ids = {
        "A": _ticket(root, ["fixable", "ship"]),
        "B": _ticket(root, ["ship"]),
        "C": _ticket(root, ["reject"]),
        "D": _ticket(root, ["ship"]),
        "F": _ticket(root, [None]),
        "G": _ticket(root, ["ship"]),
    }
    fb = lambda tid, *a, **kw: tickets.add_client_feedback(tid, *a, root=root, **kw)  # noqa: E731
    fb(ids["A"], "changes", rating=2, note="too long", iteration=1)
    fb(ids["A"], "approved", rating=4, note="loved it")
    fb(ids["B"], "approved", rating=5)
    fb(ids["C"], "changes", rating=1, note="wrong approach")
    fb(ids["D"], "changes", note="wrong ending")
    fb(ids["F"], "changes", note="wrong crop")
    fb(ids["F"], "approved", rating=3)
    return root, ids


def test_client_numbers(scen):
    root, ids = scen
    cl = report.build(root)["client"]
    assert (cl["tickets"], cl["entries"]) == (5, 7)
    assert cl["approval"] == {"approved": 3, "tickets": 5, "pct": 60.0}
    assert cl["rounds"] == {"approved_tickets": 3, "never_approved": 2, "median": 1.0}
    assert cl["rating"] == {"rated": 5, "avg": 3.0}
    assert {(c["ticket_id"], c["note"]) for c in cl["change_requests"]} == {
        (ids["A"], "too long"), (ids["C"], "wrong approach"), (ids["D"], "wrong ending"), (ids["F"], "wrong crop")}
    assert cl["agreement"]["compared"] == 5 and cl["agreement"]["matched"] == 4
    assert cl["agreement"]["unreviewed"] == 2 and cl["agreement"]["pct"] == 80.0
    assert cl["agreement"]["mismatches"] == [
        {"ticket_id": ids["D"], "session": 1, "iteration": 1, "operator": "ship", "client": "changes"}]


def test_client_text_section(scen):
    root, ids = scen
    text = report.format_text(report.build(root))
    assert "6. Client feedback" in text
    assert "client approval rate: 3/5 (60%)" in text
    assert "rounds until approval: median 1 (3 approved, 2 not yet)" in text
    assert "average rating: 3 (5 rated reactions)" in text
    assert "agreement with operator verdict: 4/5 (80%), 2 unreviewed" in text
    assert f"{ids['A']} s1·it1 ★2: too long" in text
    assert f"disagree: {ids['D']} s1·it1: operator ship, client changes" in text


def test_since_scopes_client_feedback_by_session_start(scen):
    root, _ = scen
    assert report.build(root, since=date(2000, 1, 1))["client"] == report.build(root)["client"]
    empty = report.build(root, since=date(2999, 1, 1))["client"]
    assert empty["tickets"] == 0 and empty["approval"]["pct"] is None and empty["agreement"]["pct"] is None
    assert "none yet" in report.format_text(report.build(root, since=date(2999, 1, 1)))


def test_no_feedback_says_so(tmp_path):
    root = tmp_path / "tickets"
    root.mkdir()
    _ticket(root, ["ship"])
    text = report.format_text(report.build(root))
    assert "6. Client feedback" in text and "recut ticket client <id>" in text
    assert report.build(root)["client"]["approval"] == {"approved": 0, "tickets": 0, "pct": None}


def test_cli_json_has_client_section(scen, monkeypatch, capsys):
    root, _ = scen
    monkeypatch.setattr(sys, "argv", ["recut", "report", "--root", str(root), "--json"])
    main()
    data = json.loads(capsys.readouterr().out)
    assert data["client"]["approval"]["pct"] == 60.0 and data["client"]["agreement"]["pct"] == 80.0
