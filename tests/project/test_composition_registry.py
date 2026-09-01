"""Tests for composition registry: load_compositions, save_composition, create_composition, _nodes_to_json, _nodes_from_json."""

from datetime import datetime

import pytest

from recut.compositor.effects import Fade, Reverb
from recut.compositor.nodes import Clip, Node, XFade
from recut.project import (
    _nodes_from_json,
    _nodes_to_json,
    create_composition,
    load_compositions,
    save_composition,
)


@pytest.fixture
def comp_dir(tmp_path, monkeypatch):
    """Isolated COMPOSITIONS_DIR; patches recut.project.COMPOSITIONS_DIR."""
    compositions_dir = tmp_path / "compositions"
    import recut.project as proj

    monkeypatch.setattr(proj, "COMPOSITIONS_DIR", compositions_dir)
    return compositions_dir


# ---------------------------------------------------------------------------
# load_compositions
# ---------------------------------------------------------------------------


def test_load_empty_when_no_dir(comp_dir):
    assert load_compositions() == {}


def test_save_and_load_roundtrip(comp_dir):
    comp = create_composition("my_edit", sources=["track_a"])
    comp.nodes = [Clip("verse"), XFade(beats=4)]
    save_composition(comp)

    loaded = load_compositions()
    assert "my_edit" in loaded
    result = loaded["my_edit"]
    assert result.name == "my_edit"
    assert result.sources == ["track_a"]
    assert len(result.nodes) == 2
    assert isinstance(result.nodes[0], Clip)
    assert isinstance(result.nodes[1], XFade)


# ---------------------------------------------------------------------------
# _nodes_to_json / _nodes_from_json
# ---------------------------------------------------------------------------


def test_nodes_to_json_clip():
    clip = Clip("chorus", index=2, source="track_a", bars=8)
    result = _nodes_to_json([clip])
    assert len(result) == 1
    d = result[0]
    assert d["type"] == "clip"
    assert d["segment_name"] == "chorus"
    assert d["index"] == 2
    assert d["source"] == "track_a"
    assert d["bars"] == 8
    assert d["fx"] == []


def test_nodes_to_json_xfade():
    xfade = XFade(ms=1000.0, curve="linear", beats=4)
    result = _nodes_to_json([xfade])
    assert len(result) == 1
    d = result[0]
    assert d["type"] == "xfade"
    assert d["ms"] == 1000.0
    assert d["curve"] == "linear"
    assert d["beats"] == 4


def test_nodes_from_json_roundtrip():
    nodes = [Clip("verse", index=1, bars=4), XFade(ms=500.0, beats=2)]
    serialized = _nodes_to_json(nodes)
    restored = _nodes_from_json(serialized)

    assert len(restored) == 2
    assert isinstance(restored[0], Clip)
    assert isinstance(restored[1], XFade)
    assert restored[0].segment_name == "verse"
    assert restored[0].bars == 4
    assert restored[1].ms == 500.0
    assert restored[1].beats == 2


def test_nodes_from_json_roundtrip_with_fx():
    fade = Fade(vol_start=0.0, vol_end=1.0, curve="linear")
    reverb = Reverb(wetness=0.3, reverb_type="room")
    nodes: list[Node] = [Clip("verse", fx=[fade, reverb])]
    serialized = _nodes_to_json(nodes)
    restored = _nodes_from_json(serialized)

    assert len(restored) == 1
    assert isinstance(restored[0], Clip)
    restored_fx = restored[0].fx
    assert restored_fx == [fade, reverb]
    assert restored_fx[0].to_fn()  # rebuilt into a real, usable Effect, not a dict


# ---------------------------------------------------------------------------
# create_composition
# ---------------------------------------------------------------------------


def test_create_composition():
    comp = create_composition("test_comp")
    assert comp.name == "test_comp"
    assert comp.nodes == []
    assert comp.sources == []
    assert isinstance(comp.created, datetime)


def test_create_composition_with_sources():
    comp = create_composition("mashup", sources=["track_a", "track_b"])
    assert comp.sources == ["track_a", "track_b"]
