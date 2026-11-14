"""L2: report overview (headline, turnaround, cost, baseline split, weekly trend), `--html` page, `/report` route.

Fixture (all timestamps written by hand; UTC). Hand-computed expectations:

  demo  agent `demo`, ship                                   -> never counted
  BASE  baseline (legacy agent), 2026-10-15, fixable; client approved ★3
  T1    W45  created 11-03 10:00; render 10:30; ship (it1) 12:00; client approved ★5 "Great cut" 11-04 10:00; $2
  T2    W45  created 11-04 09:00; fixable it1, ship it2 13:00; client changes ★2 "too long" 11-05, approved ★4 11-06 09:00; $4
  T3    W46  created 11-10 08:00; s1 reject, s2 ship 16:00 (2 rounds); no feedback, no usage
  T4    W46  created 11-11 08:00; ship 09:00 (opus); $1
  T5    W46  created 11-12; fixable only (not shipped); no usage

Real tickets 6 (1 baseline + 5). Reviewed 6, shipped 4 (T1-T4) -> 67 %. First-attempt ship: T1, T4 -> 2/6.
Client approval (last reaction): BASE, T1, T2 -> 3/3. Ratings 3,5,2,4 -> 3.5 (n=4). Rounds to ship 1,2,2,1 -> 1.5.
Turnaround created->ship (system): 2 h, 4 h, 8 h, 1 h -> median 3 h (10800 s). created->approved: 24 h, 48 h -> 36 h.
Cost per shipped (T1 2, T2 4, T4 1) -> median $2; total $7; sessions without usage: T3 s1, T3 s2, T5 s1.
"""

import json
import re
import sys

import pytest
from fastapi.testclient import TestClient

from recut import report
from recut.cli import main
from recut.report_html import render_html
from recut.server.app import create_app


def _w(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


def _ticket(root, tid, created, sessions, feedback=(), events=(), usage=None):
    """sessions: [(agent, model, started, [(verdict, reviewed_at or None), ...])]; usage: {session n: dict}."""
    d = root / tid
    _w(d / "request.json", {"id": tid, "created_at": created, "text": "SECRET REQUEST TEXT",
                            "client_name": "Jane Client", "client_contact": "jane@example.org", "files": {}})
    for n, (agent, model, started, reviews) in enumerate(sessions, 1):
        sd = d / "sessions" / str(n)
        _w(sd / "meta.json", {"started_at": started, "agent": agent, "model": model})
        for k, (verdict, at) in enumerate(reviews, 1):
            _w(sd / "iterations" / str(k) / "review.json", {"iteration": k, "verdict": verdict, "reviewed_at": at})
        if usage and n in usage:
            _w(sd / "usage.json", usage[n])
    if feedback:
        (d / "client_feedback.jsonl").write_text(
            "".join(json.dumps({"session": 1, "iteration": 1, **fb}) + "\n" for fb in feedback))
    if events:
        (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def _usage(model, out_tokens, cost, dur):
    return {"model": model, "models": {model: {"input_tokens": 10, "output_tokens": out_tokens,
                                               "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": cost}},
            "input_tokens": 10, "output_tokens": out_tokens, "cache_read_tokens": 0, "cache_write_tokens": 0,
            "cost_usd": cost, "duration_s": dur, "turns": 3}


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "tickets"
    r.mkdir()
    s = "claude-sonnet-5-5"
    _ticket(r, "demo-1", "2026-11-03T08:00:00+00:00", [("demo", None, "2026-11-03T08:00:00+00:00",
                                                         [("ship", "2026-11-03T08:05:00+00:00")])])
    _ticket(r, "base-1", "2026-10-15T00:00:00+00:00",
            [("legacy-pre-refactor", None, "2026-10-15T00:00:00+00:00", [("fixable", None)])],
            feedback=[{"at": "2026-10-15T00:00:00+00:00", "decision": "approved", "rating": 3}])
    _ticket(r, "t1", "2026-11-03T10:00:00+00:00", [("a", s, "2026-11-03T10:05:00+00:00",
                                                    [("ship", "2026-11-03T12:00:00+00:00")])],
            feedback=[{"at": "2026-11-04T10:00:00+00:00", "decision": "approved", "rating": 5, "note": "Great cut"}],
            events=[{"ts": "2026-11-03T10:30:00+00:00", "op": "rendered", "n": 1, "k": 1}],
            usage={1: _usage(s, 1000, 2.0, 600)})
    _ticket(r, "t2", "2026-11-04T09:00:00+00:00", [("a", s, "2026-11-04T09:05:00+00:00",
                                                    [("fixable", "2026-11-04T11:00:00+00:00"),
                                                     ("ship", "2026-11-04T13:00:00+00:00")])],
            feedback=[{"at": "2026-11-05T09:00:00+00:00", "decision": "changes", "rating": 2, "note": "too long"},
                      {"at": "2026-11-06T09:00:00+00:00", "decision": "approved", "rating": 4, "note": "Loved the ending"}],
            events=[{"ts": "2026-11-04T09:20:00+00:00", "op": "rendered", "n": 1, "k": 1}],
            usage={1: _usage(s, 2000, 4.0, 1200)})
    _ticket(r, "t3", "2026-11-10T08:00:00+00:00",
            [("a", s, "2026-11-10T08:05:00+00:00", [("reject", "2026-11-10T10:00:00+00:00")]),
             ("a", s, "2026-11-10T11:00:00+00:00", [("ship", "2026-11-10T16:00:00+00:00")])])
    _ticket(r, "t4", "2026-11-11T08:00:00+00:00", [("a", "claude-opus-5", "2026-11-11T08:05:00+00:00",
                                                    [("ship", "2026-11-11T09:00:00+00:00")])],
            usage={1: _usage("claude-opus-5", 500, 1.0, 300)})
    _ticket(r, "t5", "2026-11-12T08:00:00+00:00", [("a", s, "2026-11-12T08:05:00+00:00",
                                                    [("fixable", "2026-11-12T09:00:00+00:00")])])
    return r


def test_headline_numbers_and_demo_exclusion(root):
    o = report.build(root)["overview"]
    h = o["headline"]
    assert o["demo_excluded"] == 1
    assert (h["tickets"], h["reviewed"], h["shipped"]["value"]) == (6, 6, 4)
    assert h["ship_rate"] == {"value": 66.7, "num": 4, "n": 6}
    assert h["first_attempt_ship"] == {"value": 33.3, "num": 2, "n": 6}
    assert h["client_approval"] == {"value": 100.0, "num": 3, "n": 3}
    assert h["client_rating"] == {"value": 3.5, "n": 4}
    assert h["rounds_to_ship"] == {"value": 1.5, "n": 4}
    assert h["turnaround_ship_s"] == {"value": 10800.0, "n": 4}
    assert h["turnaround_approved_s"] == {"value": 129600.0, "n": 2}
    assert h["cost_per_shipped_usd"] == {"value": 2.0, "n": 3}
    # the classic sections skip the demo too
    assert report.build(root)["tickets"] == 6


def test_turnaround_section(root):
    t = report.build(root)["overview"]["turnaround"]
    assert t["created_to_first_render"]["n"] == 2 and t["created_to_first_render"]["value"] == 1500.0  # 30 + 20 min
    assert t["created_to_first_ship"]["p90"] == 28800.0
    assert t["ship_to_client_answer"]["n"] == 2 and t["ship_to_client_answer"]["value"] == (22 * 3600 + 20 * 3600) / 2
    assert t["created_to_client_approved"]["value"] == 129600.0


def test_cost_section(root):
    c = report.build(root)["overview"]["cost"]
    assert "API-equivalent" in c["label"]
    assert c["total_usd"] == 7.0 and c["output_tokens"] == 3500 and c["duration_s"] == 2100.0
    assert c["per_ticket_usd"] == {"value": 2.0, "n": 3, "mean": 2.33}
    assert c["no_usage_data"] == ["t3 s1", "t3 s2", "t5 s1"]
    models = {m["model"]: m for m in c["per_model"]}
    assert models["claude-sonnet-5-5"]["cost_usd"] == 6.0 and models["claude-opus-5"]["sessions"] == 1


def test_baseline_split_and_weekly(root):
    o = report.build(root)["overview"]
    assert o["baseline"]["tickets"] == 1 and o["system"]["tickets"] == 5
    assert o["baseline"]["ship_rate"]["value"] == 0.0 and o["baseline"]["client_approval"]["num"] == 1
    assert o["baseline"]["turnaround_ship_s"]["n"] == 0 and o["baseline"]["cost_per_shipped_usd"]["n"] == 0
    assert o["system"]["ship_rate"] == {"value": 80.0, "num": 4, "n": 5}
    w45, w46 = o["weekly"]
    assert (w45["week"], w45["tickets"], w46["week"], w46["tickets"]) == ("2026-W45", 2, "2026-W46", 3)
    assert w45["ship_rate"]["value"] == 100.0 and w46["ship_rate"] == {"value": 66.7, "num": 2, "n": 3}
    assert w45["client_approval"]["n"] == 2 and w46["client_approval"]["n"] == 0
    assert w46["rounds_to_ship"] == {"value": 1.5, "n": 2}
    assert o["rounds_distribution"] == {"shipped": {"1": 2, "2": 2}, "not_shipped": 2}  # BASE and T5


def test_text_marks_small_n(root):
    text = report.format_text(report.build(root))
    assert text.startswith("Headline: 6 real tickets (1 baseline, 5 ticket system), 1 demo excluded")
    assert "66% (4/6, n=6)" in text or "67% (4/6, n=6)" in text
    assert "too few to judge" in text  # rating n=4, approval n=3, ...
    assert "baseline (pre-refactor)" in text and "ticket system" in text
    assert "no usage data: t3 s1, t3 s2, t5 s1" in text
    assert "API-equivalent" in text and "2026-W45" in text
    # n >= 5 is not flagged: ship rate over 6 reviewed tickets
    line = next(ln for ln in text.splitlines() if ln.strip().startswith("ship rate"))
    assert "too few" not in line
    rating = next(ln for ln in text.splitlines() if "average client rating" in ln)
    assert "too few to judge" in rating


def test_json_has_overview(root, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["recut", "report", "--root", str(root), "--json"])
    main()
    assert json.loads(capsys.readouterr().out)["overview"]["headline"]["tickets"] == 6


def test_html_content_and_self_contained(root):
    html = render_html(report.build(root))
    assert "<svg" in html and "prefers-color-scheme" in html and 'name="viewport"' in html
    for needle in ("67%", "100%", "3.5/5", "1.5", "3.0 h", "$2.00", "2026-W45", "2026-W46", "n=6",
                   "too few to judge", "API-equivalent", "baseline (pre-refactor)", "Great cut", "2026-10-15 to 2026-11-12"):
        assert needle in html, needle
    assert not re.search(r"https?://", html, re.I) and "<script" not in html and "<link" not in html
    for secret in ("SECRET REQUEST TEXT", "Jane Client", "jane@example.org", "demo-1", "base-1"):
        assert secret not in html


def test_html_empty_root(tmp_path):
    html = render_html(report.build(tmp_path))
    assert "No ticket-system tickets yet" in html


def test_cli_html_out(root, tmp_path, capsys, monkeypatch):
    out = tmp_path / "r.html"
    monkeypatch.setattr(sys, "argv", ["recut", "report", "--root", str(root), "--html", "--out", str(out)])
    main()
    assert out.read_text().startswith("<!doctype html>") and "wrote" in capsys.readouterr().out


def test_report_route(root):
    c = TestClient(create_app(root))
    r = c.get("/report")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "recut results" in r.text and "2026-W45" in r.text
