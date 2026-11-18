"""CLI `recut ticket share` (regression: its handler was lost in a merge) and `recut ticket export`."""

import shutil
import subprocess
import sys

import pytest

from recut import tickets
from recut.contracts import Review


def run_cli(args, root, extra_env=None):
    import os
    env = {**os.environ, "RECUT_TICKETS_DIR": str(root), "RECUT_AUTOSYNC": "0", **(extra_env or {})}
    return subprocess.run([sys.executable, "-m", "recut.cli", "ticket", *args],
                          capture_output=True, text=True, env=env)


@pytest.fixture
def shipped(tmp_path, demo):
    droot, dtid = demo
    root = tmp_path / "tickets"
    shutil.copytree(droot / dtid, root / dtid)
    tickets.save_review(dtid, 1, Review(iteration=2, verdict="ship"), root)
    return root, dtid


def test_cli_share_prints_a_client_link(shipped):
    root, tid = shipped
    r = run_cli(["share", tid], root, {"RECUT_PUBLIC_URL": "https://app.example.com"})
    assert r.returncode == 0, r.stderr
    assert "https://app.example.com/s/" in r.stdout
    assert tickets.load_share(tid, root).iteration == 2


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_export_mp3_to_env_folder(shipped, tmp_path):
    root, tid = shipped
    out_dir = tmp_path / "Google Drive" / "recut"
    r = run_cli(["export", tid], root, {"RECUT_EXPORT_DIR": str(out_dir)})
    assert r.returncode == 0, r.stderr
    files = list(out_dir.glob(f"{tid}_s1-it2_*.mp3"))
    assert len(files) == 1 and files[0].stat().st_size > 10_000
    assert any(e["op"] == "exported" for e in tickets.ticket_timeline(tid, root))


def test_export_wav_and_refuses_without_ship(tmp_path, demo):
    droot, dtid = demo
    root = tmp_path / "tickets"
    shutil.copytree(droot / dtid, root / dtid)
    for p in root.glob(f"{dtid}/sessions/*/iterations/*/review.json"):
        p.unlink()
    for p in root.glob(f"{dtid}/sessions/*/review.json"):
        p.unlink()
    with pytest.raises(ValueError, match="ship"):
        tickets.export_cut(dtid, tmp_path / "out", root=root)
    out = tickets.export_cut(dtid, tmp_path / "out", fmt="wav", session=1, iteration=1, root=root)
    assert out.suffix == ".wav" and out.exists()


def test_export_named_after_client(shipped, tmp_path):
    import json
    root, tid = shipped
    rp = root / tid / "request.json"
    req = json.loads(rp.read_text())
    req["client_name"] = "Ježci: čerti"
    rp.write_text(json.dumps(req))
    out = tickets.export_cut(tid, tmp_path / "out", fmt="wav", session=1, iteration=2, root=root)
    assert out.name == "Ježci - čerti_it2.wav"
    again = tickets.export_cut(tid, tmp_path / "out", fmt="wav", session=1, iteration=2, root=root)
    assert again == out  # re-exporting the same cut replaces its own file


def test_export_never_overwrites_another_tickets_file(shipped, tmp_path):
    import json
    root, tid = shipped
    rp = root / tid / "request.json"
    req = json.loads(rp.read_text())
    req["client_name"] = "Ježci: čerti"
    rp.write_text(json.dumps(req))
    (tmp_path / "out").mkdir()
    other = tmp_path / "out" / "Ježci - čerti_it2.wav"  # same client, another ticket
    other.write_bytes(b"other cut")
    out = tickets.export_cut(tid, tmp_path / "out", fmt="wav", session=1, iteration=2, root=root)
    assert out.name == f"Ježci - čerti_it2_{tid}.wav" and other.read_bytes() == b"other cut"
    req["client_name"] = ":::"  # nothing usable left: the ticket-id name
    rp.write_text(json.dumps(req))
    assert tickets.export_cut(tid, tmp_path / "out", fmt="wav", session=1, iteration=2, root=root).name.startswith(tid)
