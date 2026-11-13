"""Agent-process enforcement: intent.json + plan.notes warnings, the work instructions, the
transcript Stop hook (scripts/hooks/copy_transcript.sh)."""

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from recut import cli, tickets
from recut.map.parser import parse_recut_map

HOOK = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "copy_transcript.sh"


@pytest.fixture()
def session(demo, tmp_path):
    """A fresh ticket with one session and two iterations, rendered with the demo plan."""
    droot, dtid = demo
    audio = droot / dtid / "inputs" / "a.mp3"
    tid = tickets.create_ticket("make it 30s", [("song.mp3", audio)], 30, root=tmp_path)
    tickets.ensure_maps(tid, tmp_path, analyze=lambda p: parse_recut_map(droot / dtid / "maps" / "a.json"))
    n = tickets.new_session(tid, agent="t", model="m", root=tmp_path)
    return tid, n, tmp_path


def set_notes(tid, n, k, notes, root):
    p = tickets.iteration_dir(tid, n, k, root) / "plan.json"
    plan = json.loads(p.read_text())
    plan["notes"] = notes
    p.write_text(json.dumps(plan))


def plan_for(tid, root):
    s = tickets.sources(tid, root)
    return {"version": 2, "sources": {k: {"file": v["file"], "map": v["map"]} for k, v in s.items()},
            "tracks": [{"id": "main", "clips": [{"id": "n1", "type": "clip", "source": "a", "segment": "intro", "index": 1}]}]}


def test_missing_intent_is_warned_and_a_valid_one_clears_it(session):
    tid, n, root = session
    k = tickets.new_iteration(tid, n, plan_for(tid, root), root=root)
    set_notes(tid, n, k, "first cut: intro only", root)
    w = tickets.process_warnings(tid, n, k, root)
    assert len(w) == 1 and "no intent.json" in w[0] and "BEFORE cutting" in w[0]
    (tickets.session_dir(tid, n, root) / "intent.json").write_text(json.dumps({"must_keep": ["chorus"]}))
    assert tickets.process_warnings(tid, n, k, root) == []
    (tickets.session_dir(tid, n, root) / "intent.json").write_text(json.dumps({"bogus": 1}))
    assert "not valid" in tickets.process_warnings(tid, n, k, root)[0]


def test_identical_notes_to_the_previous_iteration_are_warned(session):
    tid, n, root = session
    (tickets.session_dir(tid, n, root) / "intent.json").write_text("{}")
    k1 = tickets.new_iteration(tid, n, plan_for(tid, root), root=root)
    set_notes(tid, n, k1, "short intro cut", root)
    k2 = tickets.new_iteration(tid, n, root=root)  # copied: same notes
    w = tickets.process_warnings(tid, n, k2, root)
    assert len(w) == 1 and "identical to the previous iteration" in w[0] and "what you changed and why" in w[0]
    set_notes(tid, n, k2, "added a chorus because the request asked to keep it", root)
    assert tickets.process_warnings(tid, n, k2, root) == []
    # the first iteration of a later session is compared with the last of the earlier one
    n2 = tickets.new_session(tid, root=root)
    (tickets.session_dir(tid, n2, root) / "intent.json").write_text("{}")
    k3 = tickets.new_iteration(tid, n2, root=root)
    assert "identical" in tickets.process_warnings(tid, n2, k3, root)[0]


def test_empty_or_starter_notes_are_warned(session):
    tid, n, root = session
    (tickets.session_dir(tid, n, root) / "intent.json").write_text("{}")
    k = tickets.new_iteration(tid, n, plan_for(tid, root), root=root)
    assert "empty" in tickets.process_warnings(tid, n, k, root)[0]
    set_notes(tid, n, k, "starter plan — replace with the real edit", root)
    assert "empty" in tickets.process_warnings(tid, n, k, root)[0]


def test_render_prints_process_warnings(session, monkeypatch, capsys):
    tid, n, root = session
    monkeypatch.setattr(tickets, "TICKETS_DIR", root)
    k = tickets.new_iteration(tid, n, plan_for(tid, root), root=root)
    monkeypatch.setattr(tickets, "render_iteration", lambda *a, **kw: {"duration_s": 1.0, "splices": [], "issues": []})
    monkeypatch.setattr(tickets, "session_numbers", lambda *a, **kw: [n])
    monkeypatch.setattr(tickets, "iteration_numbers", lambda *a, **kw: [k])
    real = tickets.process_warnings
    monkeypatch.setattr(tickets, "process_warnings", lambda t, s, i: real(t, s, i, root))
    cli.cmd_ticket(SimpleNamespace(action="render", id=tid, session=None, iteration=None))
    out = capsys.readouterr().out
    assert "WARNING (process): no intent.json for session" in out
    assert "WARNING (process): plan.notes is empty" in out


def test_work_instructions_carry_an_intent_template_and_the_hook_note(session, capsys, monkeypatch):
    tid, n, root = session
    monkeypatch.setattr(tickets, "TICKETS_DIR", root)
    arity = {"ticket_dir": 1, "session_dir": 2, "iteration_dir": 3, "load_request": 1, "sources": 1, "load_review": 2}
    for fn, ar in arity.items():  # point the default-root helpers at the temp root
        orig = getattr(tickets, fn)
        monkeypatch.setattr(tickets, fn, lambda *a, _o=orig, _n=ar: _o(*a[:_n], root=root))
    cli._print_work_instructions(tid, n, 1)
    out = capsys.readouterr().out
    assert f"export RECUT_SESSION={tickets.session_dir(tid, n, root).resolve()}" in out
    assert "intent.json" in out and "BEFORE cutting" in out and "plan.notes" in out
    after = out[out.index("STEP 1"):]
    snippet = after[after.index("{"): after.index("}\n") + 1]
    from recut.contracts import Intent

    assert Intent.model_validate_json(snippet).target_duration_s == 30  # the template is a valid Intent
    assert "transcript.jsonl" in out


def test_mark_current_session(session):
    tid, n, root = session
    tickets.mark_current_session(tid, n, root)
    assert (root / ".current_session").read_text().strip() == str(tickets.session_dir(tid, n, root).resolve())
    assert [r.id for r in tickets.list_tickets(root)] == [tid]  # the pointer file doesn't break listing


# ---- the Stop hook ------------------------------------------------------------------------


def run_hook(stdin: str, env: dict, tmp_path):
    e = {k: v for k, v in os.environ.items() if not k.startswith("RECUT_")}
    e.update(env)
    return subprocess.run(["bash", str(HOOK)], input=stdin, text=True, env=e, capture_output=True, cwd=tmp_path)


def fake_transcript(tmp_path):
    t = tmp_path / "claude-transcript.jsonl"
    t.write_text('{"type":"user"}\n{"type":"assistant"}\n')
    return t


def test_hook_copies_the_transcript_from_stdin_json(tmp_path):
    t, sd = fake_transcript(tmp_path), tmp_path / "sess"
    sd.mkdir()
    r = run_hook(json.dumps({"session_id": "x", "transcript_path": str(t)}), {"RECUT_SESSION": str(sd)}, tmp_path)
    assert r.returncode == 0 and r.stdout == ""
    assert (sd / "transcript.jsonl").read_text() == t.read_text()
    t.write_text(t.read_text() + '{"type":"result"}\n')  # a later Stop overwrites with the longer transcript
    run_hook(json.dumps({"transcript_path": str(t)}), {"RECUT_SESSION": str(sd)}, tmp_path)
    assert (sd / "transcript.jsonl").read_text().count("\n") == 3
    assert not (sd / "transcript.jsonl.tmp").exists()


def test_hook_falls_back_to_the_current_session_pointer(tmp_path):
    t, sd, root = fake_transcript(tmp_path), tmp_path / "sess", tmp_path / "tickets"
    sd.mkdir()
    root.mkdir()
    (root / ".current_session").write_text(f"{sd}\n")
    r = run_hook(json.dumps({"transcript_path": str(t)}), {"RECUT_TICKETS_DIR": str(root)}, tmp_path)
    assert r.returncode == 0 and (sd / "transcript.jsonl").exists()


def test_hook_test_override_env_and_quiet_failures(tmp_path):
    t, sd = fake_transcript(tmp_path), tmp_path / "sess"
    sd.mkdir()
    assert run_hook("", {"RECUT_TRANSCRIPT_PATH": str(t), "RECUT_SESSION": str(sd)}, tmp_path).returncode == 0
    assert (sd / "transcript.jsonl").exists()
    # never fails the agent: no destination, no transcript, garbage stdin, missing session dir
    for stdin, env in [(json.dumps({"transcript_path": str(t)}), {"RECUT_TICKETS_DIR": str(tmp_path / "none")}),
                       ("{}", {"RECUT_SESSION": str(sd)}), ("not json", {"RECUT_SESSION": str(sd)}),
                       (json.dumps({"transcript_path": str(t)}), {"RECUT_SESSION": str(tmp_path / "gone")})]:
        r = run_hook(stdin, env, tmp_path)
        assert r.returncode == 0 and r.stdout == ""
    assert not (tmp_path / "gone").exists()
