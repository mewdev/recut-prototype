"""Q2a: Essentia QC off the critical path (render_iteration qc="fast" | "background" | "full")."""

import json
import shutil
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from recut import cli, qc, qc_essentia, tickets
from recut.audio import Audio
from recut.contracts.render import RenderInfo


@pytest.fixture
def root(demo, tmp_path):
    droot, tid = demo
    shutil.copytree(droot / tid, tmp_path / tid)
    return tmp_path, tid


@pytest.fixture
def fake_essentia(monkeypatch):
    """Essentia 'installed', its detector gated by an event so tests control when it finishes."""
    gate = threading.Event()
    gate.set()
    started = threading.Event()
    calls = []

    def detect(mono, sr):
        calls.append(1)
        started.set()
        assert gate.wait(10)
        return qc_essentia.Detections(clicks=[1.0])

    monkeypatch.setattr(qc_essentia, "available", lambda: True)
    monkeypatch.setattr(qc_essentia, "enabled", lambda: True)
    monkeypatch.setattr(qc_essentia, "detect", detect)
    return SimpleNamespace(gate=gate, started=started, calls=calls)


def _read(root, tid):
    d = tickets.iteration_dir(tid, 1, 1, root)
    return json.loads((d / "render.json").read_text())


def _wait(root, tid, state, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        data = _read(root, tid)
        if data["qc"]["essentia"] == state:
            return data
        time.sleep(0.02)
    raise AssertionError(f"qc.essentia never became {state!r}: {data['qc']['essentia']!r}")


def test_background_pending_then_done(root, fake_essentia):
    r, tid = root
    fake_essentia.gate.clear()
    tickets.render_iteration(tid, 1, 1, r, qc="background")
    data = _read(r, tid)
    assert data["qc"]["essentia"] == "pending" and data["qc"]["backend"] == "basic"
    assert (tickets.iteration_dir(tid, 1, 1, r) / "audio.wav").exists()
    fake_essentia.gate.set()
    data = _wait(r, tid, "done")
    assert data["qc"]["backend"] == "essentia" and "deep_ms" in data["qc"]
    assert data["qc"]["lufs"] is not None  # fast numbers survive the merge
    # the Essentia click hit replaced the basic detectors' issues
    assert [i["rule"] for i in data["issues"]].count("qc_backend") == 0


def test_stale_background_result_is_discarded(root, fake_essentia):
    r, tid = root
    fake_essentia.gate.clear()
    tickets.render_iteration(tid, 1, 1, r, qc="background")
    assert fake_essentia.started.wait(10)
    tickets.render_iteration(tid, 1, 1, r, qc="fast")  # newer render supersedes
    fake_essentia.gate.set()
    time.sleep(0.5)
    data = _read(r, tid)
    assert data["qc"]["essentia"] == "skipped" and data["qc"]["backend"] == "basic"


def test_full_and_fast_modes(root, fake_essentia):
    r, tid = root
    tickets.render_iteration(tid, 1, 1, r, qc="full")
    data = _read(r, tid)
    assert data["qc"]["essentia"] == "done" and data["qc"]["backend"] == "essentia"
    n = len(fake_essentia.calls)
    tickets.render_iteration(tid, 1, 1, r, qc="fast")
    data = _read(r, tid)
    assert data["qc"]["essentia"] == "skipped" and data["qc"]["backend"] == "basic"
    assert len(fake_essentia.calls) == n


def test_fast_path_never_touches_essentia(root, monkeypatch):
    r, tid = root

    def boom(*a, **k):
        raise AssertionError("essentia touched on the fast path")

    monkeypatch.setattr(qc_essentia, "available", boom)
    monkeypatch.setattr(qc_essentia, "detect", boom)
    monkeypatch.setattr(qc_essentia, "_module", boom)
    monkeypatch.setattr(qc_essentia, "enabled", lambda: False)
    out = tickets.render_iteration(tid, 1, 1, r, qc="fast")
    assert "error" not in out and out["qc"]["essentia"] == "skipped"


def test_background_without_essentia_ends_skipped(root, monkeypatch):
    r, tid = root
    monkeypatch.setattr(qc_essentia, "enabled", lambda: True)
    monkeypatch.setattr(qc_essentia, "available", lambda: False)
    tickets.render_iteration(tid, 1, 1, r, qc="background")
    _wait(r, tid, "skipped")


def test_run_qc_fast_on_plain_info():
    info = RenderInfo(duration_s=1.0, segments=[], splices=[], peak_dbfs=-6.0)
    a = Audio(np.zeros((2, 44100), dtype=np.float32) + 0.1, 44100)
    qc.run_qc(a, info, deep=False)  # plain RenderInfo has no deferred hook: must not crash


def test_cli_render_full_vs_fast(root, monkeypatch):
    r, tid = root
    seen = []
    monkeypatch.setattr(tickets, "TICKETS_DIR", r)
    monkeypatch.setattr(tickets, "render_iteration",
                        lambda *a, **kw: seen.append(kw.get("qc")) or {"duration_s": 1.0, "splices": [], "issues": []})
    monkeypatch.setattr(tickets, "process_warnings", lambda *a, **kw: [])
    for fast in (False, True):
        cli.cmd_ticket(SimpleNamespace(action="render", id=tid, session=1, iteration=1, fast=fast))
    assert seen == ["full", "fast"]
