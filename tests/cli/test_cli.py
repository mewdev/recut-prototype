"""CLI command tests — Modal and make_map are mocked."""

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from recut.cli import cmd_analyze, cmd_compositions, cmd_map, cmd_render, cmd_status, cmd_validate

FIXTURE_MAP = Path(__file__).parent.parent / "fixtures" / "sample-map.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _args(**kwargs):
    """Build a minimal argparse.Namespace."""
    return argparse.Namespace(**kwargs)


def _mock_modal(beats=None, chords=None, structure=None, key=None):
    """Return a patcher for modal.Function.from_name that yields canned results."""
    beats = beats or {
        "bpm": 120.0,
        "beats_per_bar": 4,
        "beats": [0.5, 1.0],
        "downbeats": [0.5],
    }
    chords = chords or {"chords": [{"start": 0.0, "end": 2.0, "chord": "C:maj", "confidence": 1.0}]}
    structure = structure or {"segments": [{"start": 0.0, "end": 10.0, "label": "verse"}]}
    key = key or {"key": "C major"}

    def _from_name(_app, name):
        mock_fn = MagicMock()
        results = {"run_beats": beats, "run_chords": chords, "run_structure": structure, "run_key": key}
        mock_fn.spawn.return_value.get.return_value = results[name]
        return mock_fn

    return patch("recut.cli.Function.from_name", side_effect=_from_name)


# ---------------------------------------------------------------------------
# cmd_analyze
# ---------------------------------------------------------------------------


def test_analyze_writes_raw_json(tmp_path, monkeypatch):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"fake-audio")

    raw_dir = tmp_path / "maps" / "raw"
    audio_dir = tmp_path / "audio"
    monkeypatch.setattr("recut.cli.RAW_DIR", raw_dir)
    monkeypatch.setattr("recut.cli.AUDIO_DIR", audio_dir)

    with _mock_modal():
        cmd_analyze(_args(audio=str(audio)))

    out = raw_dir / "song.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["bpm"] == 120.0
    assert data["beats_per_bar"] == 4
    assert data["key"] == "C major"
    assert "_sources" in data


def test_analyze_copies_audio(tmp_path, monkeypatch):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"fake-audio")

    raw_dir = tmp_path / "maps" / "raw"
    audio_dir = tmp_path / "audio"
    monkeypatch.setattr("recut.cli.RAW_DIR", raw_dir)
    monkeypatch.setattr("recut.cli.AUDIO_DIR", audio_dir)

    with _mock_modal():
        cmd_analyze(_args(audio=str(audio)))

    assert (audio_dir / "song.mp3").exists()


def test_analyze_missing_file_prints_error(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("recut.cli.RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr("recut.cli.AUDIO_DIR", tmp_path / "audio")

    cmd_analyze(_args(audio=str(tmp_path / "missing.mp3")))

    assert "Error" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_map
# ---------------------------------------------------------------------------


def test_map_processes_needs_map_sources(tmp_path, monkeypatch):
    from recut.map.parser import parse_recut_map
    from recut.project import Source

    map_dir = tmp_path / "maps" / "enriched"
    map_dir.mkdir(parents=True)
    raw_dir = tmp_path / "maps" / "raw"
    raw_dir.mkdir(parents=True)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True)

    audio_file = audio_dir / "song_a.mp3"
    audio_file.write_bytes(b"fake")
    raw_file = raw_dir / "song_a.json"
    raw_file.write_text("{}")

    monkeypatch.setattr("recut.cli.MAP_DIR", map_dir)
    monkeypatch.setattr("recut.cli.RAW_DIR", raw_dir)

    pending_source = Source(
        name="song_a", audio_path=audio_file, music_map=None, status="needs_map"
    )
    mock_map = parse_recut_map(FIXTURE_MAP)

    with patch("recut.cli.load_project_sources", return_value={"song_a": pending_source}):
        with patch("recut.cli.make_map", return_value=mock_map):
            cmd_map(_args())

    assert (map_dir / "song_a.json").exists()


def test_map_nothing_to_do(capsys):
    with patch("recut.cli.load_project_sources", return_value={}):
        cmd_map(_args())

    assert "Nothing to map" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_status
# ---------------------------------------------------------------------------


def test_status_prints_sorted_by_status(capsys):
    from recut.project import Source

    sources = {
        "song_b": Source(name="song_b", audio_path=Path("b.mp3"), music_map=None, status="ready"),
        "song_a": Source(name="song_a", audio_path=Path("a.mp3"), music_map=None, status="needs_analysis"),
    }

    with patch("recut.cli.load_project_sources", return_value=sources):
        cmd_status(_args())

    out = capsys.readouterr().out
    assert "song_a" in out
    assert "song_b" in out
    # needs_analysis sorts before ready alphabetically
    assert out.index("needs_analysis") < out.index("ready")


def test_status_empty_registry(capsys):
    with patch("recut.cli.load_project_sources", return_value={}):
        cmd_status(_args())

    assert "No sources" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_compositions
# ---------------------------------------------------------------------------


def test_compositions_lists_by_created(capsys):
    from datetime import datetime

    from recut.project import Composition

    comps = {
        "edit_b": Composition(name="edit_b", sources=["track_a"], nodes=[], created=datetime(2026, 8, 21, 12, 0)),
        "edit_a": Composition(name="edit_a", sources=[], nodes=[], created=datetime(2026, 8, 20, 10, 0)),
    }

    with patch("recut.cli.load_compositions", return_value=comps):
        cmd_compositions(_args())

    out = capsys.readouterr().out
    assert "edit_a" in out
    assert "edit_b" in out
    assert out.index("edit_a") < out.index("edit_b")


def test_compositions_empty(capsys):
    with patch("recut.cli.load_compositions", return_value={}):
        cmd_compositions(_args())

    assert "No compositions" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# cmd_validate / cmd_render
# ---------------------------------------------------------------------------


def _source_with_map(tmp_path, sr=22050, duration_s=5.0):
    import numpy as np
    import soundfile as sf

    from recut.map.parser import parse_recut_map
    from recut.project import Source

    audio_path = tmp_path / "song.wav"
    sf.write(audio_path, np.zeros(int(sr * duration_s)), sr)
    return Source(
        name="song", audio_path=audio_path, music_map=parse_recut_map(FIXTURE_MAP), status="ready"
    )


def _patch_registries(composition, source):
    return (
        patch("recut.cli.load_compositions", return_value={composition.name: composition}),
        patch("recut.cli.load_project_sources", return_value={"song": source}),
    )


def test_validate_ok_composition(tmp_path, capsys):
    from recut.compositor.nodes import Clip
    from recut.project import Composition

    source = _source_with_map(tmp_path)
    composition = Composition(name="edit", sources=["song"], nodes=[Clip("intro")], created=None)

    p1, p2 = _patch_registries(composition, source)
    with p1, p2:
        cmd_validate(_args(name="edit"))  # does not raise SystemExit — no error-severity issues

    assert "error" not in capsys.readouterr().out


def test_validate_bad_composition_exits(tmp_path, capsys):
    from recut.compositor.nodes import Clip
    from recut.project import Composition

    source = _source_with_map(tmp_path)
    composition = Composition(
        name="edit", sources=["song"], nodes=[Clip("chorus", bars=100)], created=None
    )

    p1, p2 = _patch_registries(composition, source)
    with pytest.raises(SystemExit):
        with p1, p2:
            cmd_validate(_args(name="edit"))

    assert "error" in capsys.readouterr().out


def test_render_writes_output_file(tmp_path, capsys, monkeypatch):
    from recut.compositor.nodes import Clip
    from recut.project import Composition

    monkeypatch.setattr("recut.cli.RENDERS_DIR", tmp_path / "renders")

    source = _source_with_map(tmp_path)
    composition = Composition(name="edit", sources=["song"], nodes=[Clip("intro")], created=None)

    out_path = tmp_path / "out.wav"
    p1, p2 = _patch_registries(composition, source)
    with p1, p2:
        cmd_render(_args(name="edit", out=str(out_path), force=False))

    assert out_path.exists()
    assert "Rendered" in capsys.readouterr().out


def test_render_aborts_on_error_without_force(tmp_path):
    from recut.compositor.nodes import Clip
    from recut.project import Composition

    source = _source_with_map(tmp_path)
    composition = Composition(
        name="edit", sources=["song"], nodes=[Clip("chorus", bars=100)], created=None
    )

    p1, p2 = _patch_registries(composition, source)
    with pytest.raises(SystemExit):
        with p1, p2:
            cmd_render(_args(name="edit", out=None, force=False))
