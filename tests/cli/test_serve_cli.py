"""`recut serve` restarts on code changes by default, so a server left running across a merge
never renders plans with stale code."""

import sys
from pathlib import Path

import pytest
import uvicorn

import recut
from recut.cli import main


@pytest.fixture
def run_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: calls.append(kw))
    return calls


def _serve(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["recut", "serve", *args])
    main()


def test_reloads_on_package_changes_by_default(run_calls, monkeypatch):
    _serve(monkeypatch)
    (kw,) = run_calls
    assert kw["reload"] is True
    assert kw["reload_dirs"] == [str(Path(recut.__file__).resolve().parent)]


def test_no_reload_opt_out(run_calls, monkeypatch):
    _serve(monkeypatch, "--no-reload")
    (kw,) = run_calls
    assert kw["reload"] is False and kw["reload_dirs"] is None


def test_old_reload_flag_still_accepted(run_calls, monkeypatch):
    _serve(monkeypatch, "--reload")
    assert run_calls[0]["reload"] is True
