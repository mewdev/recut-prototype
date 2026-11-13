"""`recut report` (B7): numbers from a hand-built ticket store. Expected values are worked out by hand
from the scenario below (see the comment on each ticket)."""

import json
import sys
from datetime import date

import pytest

from recut import report, tickets
from recut.cli import main
from recut.contracts import Review


def _issue(rule, splice=None):
    return {"severity": "warn", "rule": rule, "message": rule, "splice": splice, "node": None}


def _ticket(root, sources=1):
    files = [(f"song{i}.mp3", b"x") for i in range(sources)]
    return tickets.create_ticket("make it 30s", files, root=root)


def _session(root, tid, model, iterations):
    """iterations: dicts {sources, issues (None = no render.json), review (dict for Review, or None)}."""
    n = tickets.new_session(tid, agent="test", model=model, root=root)
    for it in iterations:
        ids = [chr(ord("a") + i) for i in range(it["sources"])]
        plan = {"version": 2, "sources": {s: {"file": f"inputs/{s}.mp3", "map": None} for s in ids},
                "tracks": [{"id": "main", "clips": [{"id": f"n{i}", "type": "clip", "source": s}
                                                   for i, s in enumerate(ids)]}]}
        k = tickets.new_iteration(tid, n, plan, root=root)
        if it.get("issues") is not None:
            d = tickets.iteration_dir(tid, n, k, root)
            (d / "render.json").write_text(json.dumps({"duration_s": 30.0, "segments": [], "splices": [],
                                                       "issues": it["issues"], "peak_dbfs": -1.0}))
        if it.get("review") is not None:
            tickets.save_review(tid, n, Review(iteration=k, **it["review"]), root=root)
    return n


def _scenario(root):
    """A  single, opus, 1 session: it1 fixable (s1 off_beat, caught by phrase_align), it2 ship.
    B  multi (2 sources), sonnet: it1 reject. s1 energy_drop caught; s2 fx_wrong + missing_primitive NOT caught.
    C  single: sonnet session 1 = it1 fixable (ending flag on s1, but ok), it2 fixable (s1 abrupt, no render
       issue); opus session 2 = it1 ship.
    D  single, sonnet: unreviewed session.
    E  multi, opus: it1 ship (phrase_align ok; ending on s9 has no review entry; qc_loudness has no splice)."""
    a = _ticket(root)
    _session(root, a, "opus", [
        {"sources": 1, "issues": [_issue("phrase_align", "s1"), _issue("phrase_align", "s2")],
         "review": {"verdict": "fixable", "splices": {"s1": {"ok": False, "tags": ["off_beat"], "note": "off beat"},
                                                      "s2": {"ok": True}}}},
        {"sources": 1, "issues": [], "review": {"verdict": "ship", "splices": {"s1": {"ok": True}}}},
    ])
    b = _ticket(root, sources=2)
    _session(root, b, "sonnet", [
        {"sources": 2, "issues": [_issue("energy_drop", "s1")],
         "review": {"verdict": "reject",
                    "splices": {"s1": {"ok": False, "tags": ["energy_drop"]},
                                "s2": {"ok": False, "tags": ["fx_wrong", "missing_primitive"],
                                       "note": "reverb wash"}},
                    "tags": ["intent_misread"], "note": "wrong section"}},
    ])
    c = _ticket(root)
    _session(root, c, "sonnet", [
        {"sources": 1, "issues": [_issue("ending", "s1")],
         "review": {"verdict": "fixable", "splices": {"s1": {"ok": True}}, "tags": ["artifact"]}},
        {"sources": 1, "issues": [],
         "review": {"verdict": "fixable",
                    "splices": {"s1": {"ok": False, "tags": ["abrupt"], "note": "hard cut, no breath"}},
                    "tags": ["abrupt"], "note": "abrupt at the splice"}},
    ])
    _session(root, c, "opus", [
        {"sources": 1, "issues": [], "review": {"verdict": "ship", "splices": {"s1": {"ok": True}}}},
    ])
    d = _ticket(root)
    _session(root, d, "sonnet", [{"sources": 1, "issues": [_issue("phrase_align", "s1")], "review": None}])
    e = _ticket(root, sources=2)
    _session(root, e, "opus", [
        {"sources": 2, "issues": [_issue("qc_loudness"), _issue("phrase_align", "s1"), _issue("ending", "s9")],
         "review": {"verdict": "ship", "splices": {"s1": {"ok": True}}}},
    ])
    return {"A": a, "B": b, "C": c, "D": d, "E": e}


@pytest.fixture
def scen(tmp_path):
    root = tmp_path / "tickets"
    root.mkdir()
    ids = _scenario(root)
    return root, ids


def _rows(data):
    return {(r["kind"], r["group"]): r for r in data["success"]}


def test_sessions_and_success_rates(scen):
    root, _ = scen
    data = report.build(root)
    assert data["tickets"] == 5
    assert data["sessions"] == {"total": 6, "reviewed": 5, "unreviewed": 1}

    rows = _rows(data)
    overall = rows[("overall", "overall")]
    assert (overall["n"], overall["ship"], overall["fixable"], overall["reject"]) == (5, 3, 1, 1)
    assert overall["success_pct"] == 60.0
    assert overall["median_iterations_to_ship"] == 1.0  # ship sessions: A=2, C(opus)=1, E=1

    opus = rows[("model", "opus")]
    assert (opus["n"], opus["ship"], opus["success_pct"], opus["median_iterations_to_ship"]) == (3, 3, 100.0, 1.0)
    sonnet = rows[("model", "sonnet")]  # the unreviewed session is left out
    assert (sonnet["n"], sonnet["ship"], sonnet["fixable"], sonnet["reject"]) == (2, 0, 1, 1)
    assert sonnet["success_pct"] == 0.0 and sonnet["median_iterations_to_ship"] is None

    single = rows[("shape", "single-song")]
    assert (single["n"], single["ship"], single["fixable"]) == (3, 2, 1)
    assert single["success_pct"] == pytest.approx(66.7, abs=0.05)
    assert single["median_iterations_to_ship"] == 1.5  # A=2, C(opus)=1

    multi = rows[("shape", "multi-song")]
    assert (multi["n"], multi["ship"], multi["reject"], multi["success_pct"]) == (2, 1, 1, 50.0)


def test_failure_tags_grouped_and_sorted(scen):
    root, _ = scen
    tags = [(t["tag"], t["group"], t["count"]) for t in report.build(root)["failure_tags"]]
    assert tags == [
        ("abrupt", "validator-catchable", 2),
        ("artifact", "engine", 1),
        ("fx_wrong", "engine", 1),
        ("missing_primitive", "engine", 1),
        ("off_beat", "validator-catchable", 1),
        ("energy_drop", "judgement", 1),
        ("intent_misread", "judgement", 1),
    ]


def test_validator_misses(scen):
    root, ids = scen
    vm = report.build(root)["validator_misses"]
    assert vm["count"] == 2 and vm["unrendered"] == 0
    found = {(i["ticket_id"], i["session"], i["iteration"], i["splice"]) for i in vm["items"]}
    # B it1 s2: bad, no issue on s2. C session 1 it2 s1: bad, the render has no issues.
    assert found == {(ids["B"], 1, 1, "s2"), (ids["C"], 1, 2, "s1")}
    b_miss = next(i for i in vm["items"] if i["ticket_id"] == ids["B"])
    assert b_miss["tags"] == ["fx_wrong", "missing_primitive"]


def test_check_accuracy(scen):
    root, _ = scen
    data = report.build(root)
    rows = {r["rule"]: r for r in data["check_accuracy"]}
    assert rows["phrase_align"] == {"rule": "phrase_align", "flagged": 3, "bad": 1, "ok": 2, "unrated": 0,
                                    "precision_pct": 33.3}
    assert rows["ending"] == {"rule": "ending", "flagged": 2, "bad": 0, "ok": 1, "unrated": 1,
                              "precision_pct": 0.0}
    assert rows["energy_drop"]["precision_pct"] == 100.0
    assert "qc_loudness" not in rows  # no splice: cannot be checked against splice marks
    assert [r["rule"] for r in data["check_accuracy"]] == ["phrase_align", "ending", "energy_drop"]


def test_worst_sessions(scen):
    root, ids = scen
    worst = report.build(root)["worst_sessions"]
    assert [w["ticket_id"] for w in worst] == [ids["C"], ids["B"], ids["A"]]  # by without-ship, then bad splices
    c = worst[0]
    assert (c["session"], c["model"], c["result"], c["iterations_without_ship"], c["bad_splices"]) == \
        (1, "sonnet", "fixable", 2, 1)
    assert c["tags"] == {"abrupt": 2, "artifact": 1}
    assert c["notes"] == ["s1·it2: abrupt at the splice", "s1·it2 s1: hard cut, no breath"]
    assert c["url"] == f"http://localhost:8000/t/{ids['C']}"
    assert worst[1]["result"] == "reject" and worst[1]["bad_splices"] == 2
    assert set(worst[1]["notes"]) == {"s1·it1: wrong section", "s1·it1 s2: reverb wash"}


def test_since_filters_sessions(scen):
    root, _ = scen
    everything = report.build(root, since=date(2000, 1, 1))
    unfiltered = report.build(root)
    assert everything.pop("since") == "2000-01-01" and unfiltered.pop("since") is None
    assert everything == unfiltered
    empty = report.build(root, since=date(2999, 1, 1))
    assert empty["tickets"] == 0 and empty["sessions"]["total"] == 0 and empty["worst_sessions"] == []


def test_report_is_read_only(scen):
    root, _ = scen

    def snapshot():
        return {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in root.rglob("*") if p.is_file()}

    before = snapshot()
    report.format_text(report.build(root))
    assert snapshot() == before


def test_unrendered_bad_splices_are_skipped_not_counted_as_misses(tmp_path):
    root = tmp_path / "tickets"
    root.mkdir()
    t = _ticket(root)
    _session(root, t, "opus", [{"sources": 1, "issues": None,
                                "review": {"verdict": "reject", "splices": {"s1": {"ok": False, "tags": ["off_beat"]}}}}])
    data = report.build(root)
    assert data["validator_misses"] == {"count": 0, "unrendered": 1, "items": []}
    assert data["check_accuracy"] == []


def test_text_output_sections(scen):
    root, _ = scen
    text = report.format_text(report.build(root))
    for heading in ("recut report: 5 tickets, 6 sessions (5 reviewed, 1 unreviewed)",
                    "1. Success rate", "2. Failure tags", "3. Validator misses: 2",
                    "4. Worst sessions", "5. Check accuracy"):
        assert heading in text


def test_cli_json_and_text(scen, monkeypatch, capsys):
    root, _ = scen
    monkeypatch.setattr(sys, "argv", ["recut", "report", "--root", str(root), "--json"])
    main()
    data = json.loads(capsys.readouterr().out)
    assert data["sessions"]["reviewed"] == 5 and data["validator_misses"]["count"] == 2

    monkeypatch.setattr(sys, "argv", ["recut", "report", "--root", str(root), "--since", "2999-01-01"])
    main()
    assert "0 tickets, 0 sessions" in capsys.readouterr().out


def test_cli_rejects_bad_since(scen, monkeypatch):
    root, _ = scen
    monkeypatch.setattr(sys, "argv", ["recut", "report", "--root", str(root), "--since", "yesterday"])
    with pytest.raises(SystemExit):
        main()


def test_demo_fixture(demo):
    root, _ = demo
    data = report.build(root)
    assert data["tickets"] == 1
    assert data["sessions"] == {"total": 1, "reviewed": 0, "unreviewed": 1}
    assert data["success"][0]["n"] == 0 and data["success"][0]["success_pct"] is None
    assert data["validator_misses"]["count"] == 0 and data["worst_sessions"] == []
    assert "0 reviewed, 1 unreviewed" in report.format_text(data)


def test_declared_but_unused_source_is_single_song():
    from recut.report import _used_sources

    plan = {"sources": {"a": {}, "b": {}},
            "tracks": [{"clips": [{"type": "clip", "source": "a"}, {"type": "xfade"},
                                  {"type": "clip", "source": "a"}]}]}
    assert _used_sources(plan) == {"a"}
