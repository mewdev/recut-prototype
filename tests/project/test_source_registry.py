"""Tests for load_project_sources() and verify_source_hash()."""

import json
import shutil
from pathlib import Path

import pytest

from recut.project import Source, load_project_sources, verify_source_hash

FIXTURE_MAP = Path(__file__).parent.parent / "fixtures" / "sample-map.json"


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    """Isolated .appdata directory; patches recut.project path constants."""
    audio_dir = tmp_path / "audio"
    raw_dir = tmp_path / "maps" / "raw"
    enriched_dir = tmp_path / "maps" / "enriched"
    audio_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    enriched_dir.mkdir(parents=True)

    import recut.project as proj
    monkeypatch.setattr(proj, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(proj, "MAP_DIR", enriched_dir)
    monkeypatch.setattr(proj, "RAW_DIR", raw_dir)

    return {"audio": audio_dir, "raw": raw_dir, "enriched": enriched_dir}


def _make_audio(appdata, name="song_a.mp3") -> Path:
    """Write a tiny fake audio file."""
    p = appdata["audio"] / name
    p.write_bytes(b"fake-audio-data")
    return p


def _make_map(appdata, stem="song_a", audio_hash="abc123") -> Path:
    """Copy sample fixture map, override audio_hash."""
    data = json.loads(FIXTURE_MAP.read_text())
    data["meta"]["audio_hash"] = audio_hash
    p = appdata["enriched"] / f"{stem}.json"
    p.write_text(json.dumps(data))
    return p


def _make_raw(appdata, stem="song_a") -> Path:
    """Write a minimal raw JSON file."""
    p = appdata["raw"] / f"{stem}.json"
    p.write_text(json.dumps({"segments": [], "bpm": 120}))
    return p


# ---------------------------------------------------------------------------
# load_project_sources
# ---------------------------------------------------------------------------


def test_ready_when_audio_and_map_present(appdata):
    _make_audio(appdata)
    # hash must match actual file content
    from recut.map.helpers import hash_file
    audio_path = appdata["audio"] / "song_a.mp3"
    _make_map(appdata, audio_hash=hash_file(audio_path))

    sources = load_project_sources()

    assert "song_a" in sources
    assert sources["song_a"].status == "ready"
    assert sources["song_a"].music_map is not None


def test_hash_mismatch_detected(appdata):
    _make_audio(appdata)
    _make_map(appdata, audio_hash="wrong-hash")

    sources = load_project_sources()

    assert sources["song_a"].status == "hash_mismatch"


def test_needs_map_when_raw_exists(appdata):
    _make_audio(appdata)
    _make_raw(appdata)

    sources = load_project_sources()

    assert sources["song_a"].status == "needs_map"
    assert sources["song_a"].music_map is None


def test_needs_analysis_when_no_json(appdata):
    _make_audio(appdata)

    sources = load_project_sources()

    assert sources["song_a"].status == "needs_analysis"


def test_non_audio_files_ignored(appdata):
    (appdata["audio"] / ".DS_Store").write_bytes(b"")
    (appdata["audio"] / "notes.txt").write_text("hello")

    sources = load_project_sources()

    assert sources == {}


def test_multiple_sources(appdata):
    from recut.map.helpers import hash_file
    for name in ("song_a.mp3", "song_b.wav"):
        _make_audio(appdata, name)
        stem = Path(name).stem
        _make_map(appdata, stem=stem, audio_hash=hash_file(appdata["audio"] / name))

    sources = load_project_sources()

    assert set(sources) == {"song_a", "song_b"}
    assert all(s.status == "ready" for s in sources.values())


# ---------------------------------------------------------------------------
# verify_source_hash
# ---------------------------------------------------------------------------


def test_verify_returns_true_on_match(appdata):
    from recut.map.helpers import hash_file
    audio_path = _make_audio(appdata)
    _make_map(appdata, audio_hash=hash_file(audio_path))
    sources = load_project_sources()
    assert verify_source_hash(sources["song_a"]) is True


def test_verify_returns_false_on_mismatch(appdata):
    _make_audio(appdata)
    _make_map(appdata, audio_hash="wrong")
    sources = load_project_sources()
    assert verify_source_hash(sources["song_a"]) is False


def test_verify_returns_false_when_no_map(appdata):
    audio_path = _make_audio(appdata)
    source = Source(
        name="song_a", audio_path=audio_path, music_map=None, status="needs_analysis"
    )
    assert verify_source_hash(source) is False
