"""`recut ticket client` (C0). Tickets go in the isolated tickets folder the test conftest sets up."""

import sys

import pytest

from recut import tickets
from recut.cli import main
from recut.contracts import Review
from recut.paths import TICKETS_DIR


@pytest.fixture
def ticket():
    tid = tickets.create_ticket("make it 30s", [], root=TICKETS_DIR)
    n = tickets.new_session(tid, agent="test", model="m", root=TICKETS_DIR)
    for verdict in ("fixable", "ship"):
        k = tickets.new_iteration(tid, n, {"version": 2}, root=TICKETS_DIR)
        tickets.save_review(tid, n, Review(iteration=k, verdict=verdict), root=TICKETS_DIR)
    return tid


def _run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["recut", "ticket", "client", *args])
    main()


def test_approved_defaults_to_the_shipped_iteration(ticket, monkeypatch, capsys):
    _run(monkeypatch, ticket, "--approved", "--rating", "5", "--note", "loved it")
    out = capsys.readouterr().out
    assert "client approved ★5 on s1·it2 (latest shipped)" in out
    assert "client_approved" in out and "note: loved it" in out
    fbs = tickets.load_client_feedback(ticket, TICKETS_DIR)
    assert [(f.session, f.iteration, f.decision, f.rating, f.note) for f in fbs] == \
        [(1, 2, "approved", 5, "loved it")]


def test_changes_with_explicit_target(ticket, monkeypatch, capsys):
    _run(monkeypatch, ticket, "--changes", "--session", "1", "--iteration", "1", "--note", "too long")
    out = capsys.readouterr().out
    assert "client changes on s1·it1 (given)" in out and "client_changes" in out
    assert tickets.load_request(ticket, TICKETS_DIR).status == "client_changes"


def test_latest_iteration_without_ship_is_said_so(monkeypatch, capsys):
    tid = tickets.create_ticket("x", [], root=TICKETS_DIR)
    n = tickets.new_session(tid, agent="test", root=TICKETS_DIR)
    tickets.new_iteration(tid, n, {"version": 2}, root=TICKETS_DIR)
    _run(monkeypatch, tid, "--changes", "--note", "wrong approach")
    assert "s1·it1 (no ship review yet: latest iteration)" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [
    [],                                   # one of --approved / --changes is required
    ["--approved", "--changes"],          # not both
    ["--approved", "--rating", "6"],      # rating 1-5
    ["--approved", "--rating", "x"],
])
def test_bad_arguments_exit(ticket, monkeypatch, argv):
    with pytest.raises(SystemExit):
        _run(monkeypatch, ticket, *argv)
    assert tickets.load_client_feedback(ticket, TICKETS_DIR) == []


def test_unknown_ticket_and_bad_target_exit_with_error(ticket, monkeypatch, capsys):
    with pytest.raises(SystemExit) as e:
        _run(monkeypatch, "20000101-none", "--approved")
    assert e.value.code == 1 and "ticket not found" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        _run(monkeypatch, ticket, "--approved", "--iteration", "7")
    assert e.value.code == 1 and "no iteration 7" in capsys.readouterr().out
