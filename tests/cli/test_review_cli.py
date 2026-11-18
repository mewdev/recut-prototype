"""`recut ticket review`: the operator's verdict, given in the agent session, saved as the same
review files the GUI writes. Tickets go in the isolated tickets folder the test conftest sets up."""

import json
import sys

import pytest

from recut import tickets
from recut.cli import REVIEW_PROVENANCE, main
from recut.paths import TICKETS_DIR


@pytest.fixture
def ticket():
    tid = tickets.create_ticket("lengthen the pauses", [], root=TICKETS_DIR)
    n = tickets.new_session(tid, agent="test", model="m", root=TICKETS_DIR)
    k = tickets.new_iteration(tid, n, {"version": 2}, root=TICKETS_DIR)
    render = {"splices": [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]}
    (tickets.iteration_dir(tid, n, k, TICKETS_DIR) / "render.json").write_text(json.dumps(render))
    return tid


def _run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["recut", "ticket", "review", *args])
    main()


def test_ship_all_ok_is_what_the_gui_loads(ticket, monkeypatch, capsys):
    _run(monkeypatch, ticket, "--verdict", "ship", "--ok", "all", "--note", "sounds right")
    assert "Recorded review ship on s1·it1" in capsys.readouterr().out
    rv = tickets.load_iteration_review(ticket, 1, 1, TICKETS_DIR)  # what the server returns
    assert rv.verdict == "ship" and all(s.ok for s in rv.splices.values()) and len(rv.splices) == 3
    assert rv.note == f"sounds right\n\n{REVIEW_PROVENANCE}" and rv.reviewed_at
    assert tickets.load_review(ticket, 1, TICKETS_DIR) == rv  # session copy for the next agent
    assert tickets.load_request(ticket, TICKETS_DIR).status == "in_review"


def test_bad_splice_with_tags(ticket, monkeypatch):
    _run(monkeypatch, ticket, "--verdict", "fixable", "--ok", "s1", "--bad", "s3:abrupt+energy_drop",
         "--tags", "duration_miss")
    rv = tickets.load_iteration_review(ticket, 1, 1, TICKETS_DIR)
    assert rv.splices["s1"].ok and not rv.splices["s3"].ok and "s2" not in rv.splices
    assert rv.splices["s3"].tags == ["abrupt", "energy_drop"] and rv.tags == ["duration_miss"]
    assert rv.note == REVIEW_PROVENANCE
    assert tickets.load_request(ticket, TICKETS_DIR).status == "needs_rework"


@pytest.mark.parametrize("argv", [
    ["--verdict", "ship", "--ok", "s9"],                 # splice not in render.json
    ["--verdict", "ship", "--bad", "s1:not_a_tag"],      # tag not in TAGS
    ["--verdict", "great"],                              # verdict not ship/fixable/reject
    [],                                                  # --verdict is required
])
def test_bad_arguments_exit_without_saving(ticket, monkeypatch, argv):
    with pytest.raises(SystemExit):
        _run(monkeypatch, ticket, *argv)
    assert tickets.load_iteration_review(ticket, 1, 1, TICKETS_DIR) is None


def test_unrendered_iteration_is_refused(monkeypatch, capsys):
    tid = tickets.create_ticket("x", [], root=TICKETS_DIR)
    n = tickets.new_session(tid, agent="test", root=TICKETS_DIR)
    tickets.new_iteration(tid, n, {"version": 2}, root=TICKETS_DIR)
    with pytest.raises(SystemExit):
        _run(monkeypatch, tid, "--verdict", "ship")
    assert "no render.json" in capsys.readouterr().out
