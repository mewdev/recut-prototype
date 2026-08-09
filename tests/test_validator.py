"""Tests for validator checks and validate() integration.

Uses a stub parser to avoid file I/O — checks logic only.
"""

import pytest

from compositor import Clip, Loop
from validator import validate
from validator.checks import check_duration_exceeds, check_label_exists

# --- Stub parser -----------------------------------------------------------


class StubParser:
    """Minimal MapParser stub — no file I/O, fixed segments and BPM."""

    BPM = 80.0
    SEGMENTS = {
        "intro": {"start": 0.1, "end": 3.1, "downbeats": [0.1, 3.1]},
        "verse": {"start": 3.1, "end": 36.1},
        "chorus": {"start": 36.1, "end": 60.1},
    }

    def get_segment(self, label: str, index: int = 1) -> dict:
        if label not in self.SEGMENTS or index > 1:
            raise ValueError(f"No {label!r} segment at index {index}")
        return self.SEGMENTS[label]

    def get_bpm(self) -> float:
        return self.BPM

    def bars_to_seconds(self, bars: float) -> float:
        return bars * 4 * (60.0 / self.BPM)

    def beats_to_seconds(self, beats: float) -> float:
        return beats * (60.0 / self.BPM)


@pytest.fixture
def parser():
    return StubParser()


# --- check_label_exists ----------------------------------------------------


def test_label_exists_valid(parser):
    result = check_label_exists(Clip("intro"), parser)
    assert result is None


def test_label_exists_missing(parser):
    result = check_label_exists(Clip("bridge"), parser)
    assert result is not None
    assert result.severity == "error"
    assert "bridge" in result.message


def test_label_exists_index_out_of_range(parser):
    # StubParser only has one of each — index=2 should fail
    result = check_label_exists(Clip("intro", index=2), parser)
    assert result is not None
    assert result.severity == "error"


# --- check_duration_exceeds ------------------------------------------------


def test_duration_bars_within_limit(parser):
    # intro is 3s, 1 bar at 80BPM = 3s — exactly fits
    result = check_duration_exceeds(Clip("intro", bars=1), parser)
    assert result is None


def test_duration_bars_exceeds(parser):
    result = check_duration_exceeds(Clip("intro", bars=10), parser)
    assert result is not None
    assert result.severity == "error"
    assert "bars" in result.message
    assert "intro" in result.message


def test_duration_beats_within_limit(parser):
    # intro is 3s, 2 beats at 80BPM = 1.5s — fits
    result = check_duration_exceeds(Clip("intro", beats=2), parser)
    assert result is None


def test_duration_beats_exceeds(parser):
    result = check_duration_exceeds(Clip("intro", beats=999), parser)
    assert result is not None
    assert result.severity == "error"
    assert "beats" in result.message


def test_duration_no_override(parser):
    # no bars or beats — nothing to check
    result = check_duration_exceeds(Clip("intro"), parser)
    assert result is None


def test_duration_missing_label_returns_none(parser):
    # label check handles this — duration check should skip gracefully
    result = check_duration_exceeds(Clip("nonexistent", bars=1), parser)
    assert result is None


# --- validate() integration ------------------------------------------------


def test_validate_all_valid(parser):
    results = validate(parser, Clip("intro"), Clip("verse"))
    assert results == []


def test_validate_collects_multiple_errors(parser):
    results = validate(parser, Clip("nonexistent"), Clip("intro", bars=99))
    severities = [r.severity for r in results]
    assert "error" in severities
    assert len(results) >= 2


def test_validate_loop_valid(parser):
    results = validate(parser, Loop("chorus", times=3))
    assert results == []
