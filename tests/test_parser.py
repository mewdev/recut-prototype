"""Tests for parser free functions — uses real end_of_beginning map fixture."""

import pytest

from recut.map.parser import (
    bars_to_seconds,
    beats_to_seconds,
    get_segment,
    parse_recut_map,
)

MAP = "tests/fixtures/end_of_beginning-map-v0_1.json"


@pytest.fixture
def music_map():
    return parse_recut_map(MAP)


# --- bpm -------------------------------------------------------------------


def test_bpm(music_map):
    assert music_map.bpm == 80.0


# --- bars_to_seconds -------------------------------------------------------


def test_bars_to_seconds_one_bar(music_map):
    # 4 beats * (60/80) = 3.0s
    assert bars_to_seconds(music_map, 1) == pytest.approx(3.0)


def test_bars_to_seconds_half_bar(music_map):
    assert bars_to_seconds(music_map, 0.5) == pytest.approx(1.5)


# --- beats_to_seconds ------------------------------------------------------


def test_beats_to_seconds(music_map):
    # 60/80 = 0.75s per beat
    assert beats_to_seconds(music_map, 1) == pytest.approx(0.75)


# --- get_segment -----------------------------------------------------------


def test_get_segment_has_start_end(music_map):
    seg = get_segment(music_map, "intro")
    assert seg.start is not None
    assert seg.end is not None


def test_get_segment_intro_boundaries(music_map):
    seg = get_segment(music_map, "intro")
    assert seg.start == pytest.approx(0.0)
    assert seg.end == pytest.approx(3.12)


def test_get_segment_has_downbeats(music_map):
    seg = get_segment(music_map, "intro")
    assert seg.downbeats
    assert seg.downbeats[0] == pytest.approx(0.1)


def test_get_segment_missing_label_raises(music_map):
    with pytest.raises(ValueError, match="nonexistent"):
        get_segment(music_map, "nonexistent")


def test_get_segment_index_out_of_range_raises(music_map):
    with pytest.raises(ValueError):
        get_segment(music_map, "intro", index=99)


def test_get_segment_index_selects_correct_occurrence(music_map):
    verse1 = get_segment(music_map, "verse", index=1)
    verse2 = get_segment(music_map, "verse", index=2)
    assert verse1.start != verse2.start
