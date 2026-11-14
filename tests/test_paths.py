import importlib
import subprocess

import recut.paths
from recut.paths import resolve_tickets_dir


def test_appdata_is_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("RECUT_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    p = importlib.reload(recut.paths)
    assert (p.HOME / "pyproject.toml").exists()  # repo root, not tmp_path
    assert p.APPDATA == p.HOME / ".appdata"


def test_recut_home_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("RECUT_HOME", str(tmp_path))
    p = importlib.reload(recut.paths)
    assert p.APPDATA == tmp_path.resolve() / ".appdata"
    monkeypatch.delenv("RECUT_HOME")
    importlib.reload(recut.paths)


def test_tickets_dir_resolution(tmp_path):
    home = tmp_path / "recut-prototype"
    home.mkdir()
    assert resolve_tickets_dir(home, {}) == home / ".appdata" / "tickets"  # no data repo
    data = tmp_path / "recut-data"
    data.mkdir()
    subprocess.run(["git", "init", "-q", str(data)], check=True)
    assert resolve_tickets_dir(home, {}) == data / "tickets"  # sibling data repo
    assert resolve_tickets_dir(home, {"RECUT_TICKETS_DIR": str(tmp_path / "x")}) == (tmp_path / "x").resolve()
