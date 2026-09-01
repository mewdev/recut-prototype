"""Tests for parser free functions — uses synthetic sample map fixture."""

from typing import cast

import pytest

from recut.map.parser import (
    bars_to_seconds,
    beats_to_seconds,
    get_segment,
    parse_recut_map,
)
from recut.map.schema import SegmentName

MAP = "tests/fixtures/sample-map.json"


@pytest.fixture
def music_map():
    return parse_recut_map(MAP)


# --- bpm -------------------------------------------------------------------


def test_bpm(music_map):
    assert music_map.bpm == 120.0


# --- bars_to_seconds -------------------------------------------------------


def test_bars_to_seconds_one_bar(music_map):
    # 4 beats * (60/120) = 2.0s
    assert bars_to_seconds(music_map, 1) == pytest.approx(2.0)


def test_bars_to_seconds_half_bar(music_map):
    assert bars_to_seconds(music_map, 0.5) == pytest.approx(1.0)


def test_bars_to_seconds_three_four_time(music_map):
    # non-4/4 map — was previously unreachable, schema forbade anything but "4/4"
    waltz_map = music_map.model_copy(update={"beats_per_bar": 3, "bpm": 120.0})
    # 3 beats * (60/120) = 1.5s
    assert bars_to_seconds(waltz_map, 1) == pytest.approx(1.5)


# --- beats_to_seconds ------------------------------------------------------


def test_beats_to_seconds(music_map):
    # 60/120 = 0.5s per beat
    assert beats_to_seconds(music_map, 1) == pytest.approx(0.5)


# --- get_segment -----------------------------------------------------------


def test_get_segment_has_start_end(music_map):
    seg = get_segment(music_map, "intro")
    assert seg.start is not None
    assert seg.end is not None


def test_get_segment_intro_boundaries(music_map):
    seg = get_segment(music_map, "intro")
    assert seg.start == pytest.approx(0.0)
    assert seg.end == pytest.approx(4.0)


def test_get_segment_has_downbeats(music_map):
    seg = get_segment(music_map, "intro")
    assert seg.downbeats
    assert seg.downbeats[0] == pytest.approx(0.0)


def test_get_segment_missing_label_raises(music_map):
    with pytest.raises(ValueError, match="nonexistent"):
        get_segment(music_map, cast(SegmentName, "nonexistent"))


def test_get_segment_index_out_of_range_raises(music_map):
    with pytest.raises(ValueError):
        get_segment(music_map, "intro", index=99)


def test_get_segment_index_selects_correct_occurrence(music_map):
    verse1 = get_segment(music_map, "verse", index=1)
    verse2 = get_segment(music_map, "verse", index=2)
    assert verse1.start != verse2.start
