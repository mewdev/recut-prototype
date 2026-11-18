"""ffmpeg/ffprobe are found next to the running Python when the env's bin/ is not on PATH
(recut run without activating the conda env: MP3 export failed though ffmpeg was installed)."""

import sys

from recut import intake


def _fake_env(tmp_path, monkeypatch, *names):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for n in names:
        (bin_dir / n).write_text("")
    monkeypatch.setattr(sys, "executable", str(bin_dir / "python"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    return bin_dir


def test_found_next_to_python_when_not_on_path(tmp_path, monkeypatch):
    bin_dir = _fake_env(tmp_path, monkeypatch, "ffmpeg")
    assert intake.tool("ffmpeg") == str(bin_dir / "ffmpeg")


def test_none_when_nowhere(tmp_path, monkeypatch):
    _fake_env(tmp_path, monkeypatch)
    assert intake.tool("ffprobe") is None
