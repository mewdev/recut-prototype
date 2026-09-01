import pytest

from recut.map.helpers import snap_to_downbeat


def test_snap_to_downbeat_nearer_before():
    assert snap_to_downbeat([1.0, 2.0, 3.0], 2.3) == 2.0


def test_snap_to_downbeat_nearer_after():
    assert snap_to_downbeat([1.0, 2.0, 3.0], 2.7) == 3.0


def test_snap_to_downbeat_before_first():
    assert snap_to_downbeat([1.0, 2.0, 3.0], 0.0) == 1.0


def test_snap_to_downbeat_after_last():
    assert snap_to_downbeat([1.0, 2.0, 3.0], 5.0) == 3.0


def test_snap_to_downbeat_exact_match():
    assert snap_to_downbeat([1.0, 2.0, 3.0], 2.0) == 2.0


def test_snap_to_downbeat_empty_raises():
    with pytest.raises(ValueError):
        snap_to_downbeat([], 1.0)
