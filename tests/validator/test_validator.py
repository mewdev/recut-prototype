"""Tests for validator checks and validate() integration."""

from typing import cast

import pytest

from recut.compositor import Clip
from recut.map.schema import MusicMap, SegmentName
from recut.validator import validate
from recut.validator.checks import check_duration_exceeds, check_label_exists


def _seg(name, start, end, downbeats, idx):
    return {
        "index": idx,
        "segment_name": name,
        "start": start,
        "end": end,
        "duration": round(end - start, 2),
        "bars": 1,
        "downbeats": downbeats,
        "phrases": [],
        "chords": [],
        "loudness_db": -12.0,
        "loudness_db_start": -14.0,
        "loudness_db_end": -10.0,
    }


def stub_map() -> MusicMap:
    return MusicMap.model_validate(
        {
            "path": "test.mp3",
            "bpm": 80.0,
            "beats_per_bar": 4,
            "duration": 60.1,
            "beats": [],
            "bars": [],
            "segments": [
                _seg("intro", 0.1, 3.1, [0.1, 3.1], 1),
                _seg("verse", 3.1, 36.1, [], 1),
                _seg("chorus", 36.1, 60.1, [], 1),
            ],
            "sources": {
                "beats": {"name": "madmom", "version": "0.16"},
                "chords": {"name": "chordmini", "version": "1.0"},
                "structure": {"name": "chordmini", "version": "1.0"},
            },
            "meta": {"audio_hash": "abc123", "generated_at": "2026-08-19", "map_version": "1.0"},
        }
    )


@pytest.fixture
def music_map():
    return stub_map()


# --- check_label_exists ----------------------------------------------------


def test_label_exists_valid(music_map):
    result = check_label_exists(Clip("intro"), music_map)
    assert result is None


def test_label_exists_missing(music_map):
    result = check_label_exists(Clip("bridge"), music_map)
    assert result is not None
    assert result.severity == "error"
    assert "bridge" in result.message


def test_label_exists_index_out_of_range(music_map):
    result = check_label_exists(Clip("intro", index=2), music_map)
    assert result is not None
    assert result.severity == "error"


# --- check_duration_exceeds ------------------------------------------------


def test_duration_bars_within_limit(music_map):
    # intro is 3s, 1 bar at 80BPM/4/4 = 3.0s — exactly fits
    result = check_duration_exceeds(Clip("intro", bars=1), music_map)
    assert result is None


def test_duration_bars_exceeds(music_map):
    result = check_duration_exceeds(Clip("intro", bars=10), music_map)
    assert result is not None
    assert result.severity == "error"
    assert "bars" in result.message
    assert "intro" in result.message


def test_duration_beats_within_limit(music_map):
    # intro is 3s, 2 beats at 80BPM = 1.5s — fits
    result = check_duration_exceeds(Clip("intro", beats=2), music_map)
    assert result is None


def test_duration_beats_exceeds(music_map):
    result = check_duration_exceeds(Clip("intro", beats=999), music_map)
    assert result is not None
    assert result.severity == "error"
    assert "beats" in result.message


def test_duration_no_override(music_map):
    result = check_duration_exceeds(Clip("intro"), music_map)
    assert result is None


def test_duration_missing_label_returns_none(music_map):
    result = check_duration_exceeds(Clip(cast(SegmentName, "nonexistent"), bars=1), music_map)
    assert result is None


# --- validate() integration ------------------------------------------------


def test_validate_all_valid(music_map):
    results = validate(music_map, Clip("intro"), Clip("verse"), Clip("chorus"))
    assert results == []


def test_validate_collects_multiple_errors(music_map):
    results = validate(music_map, Clip(cast(SegmentName, "nonexistent")), Clip("intro", bars=99))
    severities = [r.severity for r in results]
    assert "error" in severities
    assert len(results) >= 2


def test_validate_loop_valid(music_map):
    results = validate(music_map, Clip("intro"), Clip("chorus", loop=3))
    assert results == []
