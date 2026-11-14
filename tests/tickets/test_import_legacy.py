"""L3: `recut ticket import-legacy` turns a pre-refactor export into a baseline ticket."""

import json

import pytest

from recut import legacy_import, report, tickets
from recut.contracts import ClientFeedback, Intent, Request, Review, SessionMeta

EXPORT = "20261015-like-its-christmas-cut"


@pytest.fixture
def export(tmp_path):
    """A synthetic pre-refactor export: 2 iterations, human_fix on it1, client approval on it2."""
    d = tmp_path / "exports" / EXPORT
    (d / "iterations" / "1").mkdir(parents=True)
    (d / "iterations" / "2").mkdir(parents=True)
    (d / "request.json").write_text(json.dumps({
        "id": EXPORT, "date": "2026-10-15", "text": "keep the intro, then the later chorus",
        "target_duration_s": None,
        "sources": {"a": {"file_name": "like-its-christmas.mp3", "duration_s": 200.9}},
        "multi_song": False,
    }))
    (d / "intent.json").write_text(json.dumps({
        "target_duration_s": None, "must_keep": ["0:00-0:47"], "must_cut": [],
        "ending": "natural", "notes": "n", "unknown_key": 1,
    }))
    (d / "export.json").write_text(json.dumps({"exported_at": "2026-11-14"}))
    (d / "timeline.md").write_text("# Timeline\n")
    (d / "code_changes.md").write_text("# Code\n")
    (d / "transcript.jsonl").write_text('{"type": "user"}\n')
    comp = {"source": "like-its-christmas", "nodes": []}
    (d / "iterations" / "1" / "composition.json").write_text(json.dumps(comp))
    (d / "iterations" / "2" / "composition.json").write_text(json.dumps(comp))
    (d / "iterations" / "1" / "review.json").write_text(json.dumps({
        "iteration": 1, "verdict": "fixable", "client_approved": None,
        "splices": {"s1": {"ok": True, "tags": [], "note": "fine"}},
        "tags": ["bad_ending"], "note": "keep the silence", "human_fix": "Keep the trailing silence.",
    }))
    (d / "iterations" / "2" / "review.json").write_text(json.dumps({
        "iteration": 2, "verdict": "fixable", "client_approved": True,
        "splices": {"s1": {"ok": True, "tags": [], "note": None}},
        "tags": ["map_wrong"], "note": "unsure", "human_fix": None,
    }))
    return d


def test_import_writes_a_valid_baseline_ticket(export, tmp_path):
    root = tmp_path / "tickets"
    tid = legacy_import.import_export(export, root)
    assert tid == legacy_import.ticket_id_for(export)
    assert tid.startswith("20261015-legacy-like-its-christmas-cut-") and len(tid.rsplit("-", 1)[1]) == 4

    req = Request.model_validate_json((root / tid / "request.json").read_text())
    assert req.files == {"a": "like-its-christmas.mp3"}
    assert req.text.startswith("keep the intro") and req.target_duration_s is None
    assert req.status == "client_approved"  # last client decision (it2) wins

    s = root / tid / "sessions" / "1"
    meta = SessionMeta.model_validate_json((s / "meta.json").read_text())
    assert meta.agent == "legacy-pre-refactor" and meta.model is None
    assert meta.started_at.startswith("2026-10-15")
    intent = Intent.model_validate_json((s / "intent.json").read_text())  # unknown key dropped
    assert intent.must_keep == ["0:00-0:47"]
    for name in ("transcript.jsonl", "timeline.md", "code_changes.md"):
        assert (s / name).exists()
    assert (s / "iterations" / "1" / "composition.json").exists()
    assert not (s / "iterations" / "1" / "plan.json").exists()  # no maps in the export
    assert "skipped" in json.loads((s / "import.json").read_text())


def test_reviews_contain_only_contract_fields(export, tmp_path):
    root = tmp_path / "tickets"
    tid = legacy_import.import_export(export, root)
    it1 = json.loads((root / tid / "sessions" / "1" / "iterations" / "1" / "review.json").read_text())
    assert set(it1) == set(Review.model_fields)
    assert it1["note"] == "keep the silence\nhuman fix: Keep the trailing silence."
    assert it1["verdict"] == "fixable" and it1["tags"] == ["bad_ending"]
    it2 = tickets.load_iteration_review(tid, 1, 2, root)
    assert it2 is not None and it2.note == "unsure" and it2.verdict == "fixable"
    assert tickets.load_review(tid, 1, root).iteration == 2  # session copy = latest


def test_client_feedback_line_attached_to_approved_iteration(export, tmp_path):
    root = tmp_path / "tickets"
    tid = legacy_import.import_export(export, root)
    lines = (root / tid / "client_feedback.jsonl").read_text().splitlines()
    assert len(lines) == 1
    fb = ClientFeedback.model_validate_json(lines[0])
    assert (fb.session, fb.iteration, fb.decision, fb.rating, fb.channel) == (1, 2, "approved", None, "manual")
    assert fb.note == "imported from pre-refactor export"
    assert fb.at.startswith("2026-11-14")
    assert tickets.load_client_feedback(tid, root) == [fb]


def test_not_demo_and_not_awaiting(export, tmp_path):
    root = tmp_path / "tickets"
    tid = legacy_import.import_export(export, root)
    assert not tickets.is_demo(tid, root)
    assert tid not in {it["id"] for it in tickets.awaiting_client(root)}


def test_reimport_refused_then_forced(export, tmp_path):
    root = tmp_path / "tickets"
    tid = legacy_import.import_export(export, root)
    before = (root / tid / "request.json").read_text()
    with pytest.raises(FileExistsError):
        legacy_import.import_export(export, root)
    assert (root / tid / "request.json").read_text() == before
    (root / tid / "stray.txt").write_text("x")
    assert legacy_import.import_export(export, root, force=True) == tid
    assert not (root / tid / "stray.txt").exists()  # --force replaces the whole folder
    assert (root / tid / "request.json").read_text() == before


def test_report_counts_the_baseline_ticket(export, tmp_path):
    root = tmp_path / "tickets"
    legacy_import.import_export(export, root)
    data = report.build(root)
    assert data["tickets"] == 1
    assert data["sessions"] == {"total": 1, "reviewed": 1, "unreviewed": 0}
    overall = data["success"][0]
    assert overall["group"] == "overall" and overall["n"] == 1 and overall["fixable"] == 1
    assert data["client"]["approval"] == {"approved": 1, "tickets": 1, "pct": 100.0}
    assert data["client"]["agreement"]["mismatches"][0]["operator"] == "fixable"


def test_bad_folder_name_rejected(tmp_path):
    bad = tmp_path / "no-date-here"
    bad.mkdir()
    (bad / "request.json").write_text("{}")
    with pytest.raises(ValueError):
        legacy_import.ticket_id_for(bad)
