import importlib
import os

import recut.paths


def test_appdata_is_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("RECUT_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    p = importlib.reload(recut.paths)
    assert (p.HOME / "pyproject.toml").exists()  # repo root, not tmp_path
    assert p.TICKETS_DIR == p.HOME / ".appdata" / "tickets"


def test_recut_home_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("RECUT_HOME", str(tmp_path))
    p = importlib.reload(recut.paths)
    assert p.TICKETS_DIR == tmp_path.resolve() / ".appdata" / "tickets"
    monkeypatch.delenv("RECUT_HOME")
    importlib.reload(recut.paths)
    assert os.environ.get("RECUT_HOME") is None
