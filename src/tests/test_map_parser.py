"""Tests for OurMapParser — uses real end_of_beginning map fixture."""

import pytest

from map.parser import OurMapParser

MAP = "src/tests/fixtures/end_of_beginning-map-v0_1.json"


@pytest.fixture
def parser():
    return OurMapParser(MAP)


# --- get_bpm ---------------------------------------------------------------


def test_get_bpm(parser):
    assert parser.get_bpm() == 80.0


# --- bars_to_seconds -------------------------------------------------------


def test_bars_to_seconds_one_bar(parser):
    # 4 beats * (60/80) = 3.0s
    assert parser.bars_to_seconds(1) == pytest.approx(3.0)


def test_bars_to_seconds_half_bar(parser):
    assert parser.bars_to_seconds(0.5) == pytest.approx(1.5)


# --- beats_to_seconds ------------------------------------------------------


def test_beats_to_seconds(parser):
    # 60/80 = 0.75s per beat
    assert parser.beats_to_seconds(1) == pytest.approx(0.75)


# --- get_segment -----------------------------------------------------------


def test_get_segment_returns_start_end(parser):
    seg = parser.get_segment("intro")
    assert "start" in seg
    assert "end" in seg


def test_get_segment_intro_boundaries(parser):
    seg = parser.get_segment("intro")
    assert seg["start"] == pytest.approx(0.0)
    assert seg["end"] == pytest.approx(3.12)


def test_get_segment_returns_audio_start_when_downbeats(parser):
    seg = parser.get_segment("intro")
    assert "audio_start" in seg
    assert seg["audio_start"] == pytest.approx(0.1)


def test_get_segment_missing_label_raises(parser):
    with pytest.raises(ValueError, match="nonexistent"):
        parser.get_segment("nonexistent")


def test_get_segment_index_out_of_range_raises(parser):
    with pytest.raises(ValueError):
        parser.get_segment("intro", index=99)


def test_get_segment_index_selects_correct_occurrence(parser):
    verse1 = parser.get_segment("verse", index=1)
    verse2 = parser.get_segment("verse", index=2)
    assert verse1["start"] != verse2["start"]
