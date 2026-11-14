"""M0 map fixes: first-section lead-in, beat-grid tempo, NaN-free loudness (synthetic data)."""

import json
import warnings
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from recut.contracts import ClipNode
from recut.engine import _clip_bounds
from recut.map.helpers import loudness_rms_db
from recut.map.make_map import build_segment
from recut.map.make_map import run as make_map
from recut.map.parser import parse_recut_map, parse_recut_map_dict
from recut.map.schema import LOUDNESS_FLOOR_DB
from recut.map.tempo import bpm_from_beats

SR = 8000
FIXTURE_MAP = Path(__file__).parent.parent / "fixtures" / "sample-map.json"


def _raw(bpm=120.0, first_downbeat=1.0, seg_bounds=((0.0, 5.0, "intro"), (5.0, 9.0, "verse"),
                                                    (9.0, 12.0, "silence"))):
    beats = [round(first_downbeat + 0.5 * i, 3) for i in range(20)]  # 120 bpm grid
    return {
        "path": "x.wav", "bpm": bpm, "beats_per_bar": 4,
        "beats": beats, "downbeats": beats[::4],
        "segments": [{"start": a, "end": b, "label": n} for a, b, n in seg_bounds],
        "chords": [], "key": "C major",
        "_sources": {"beats": "madmom", "chords": "c", "structure": "s", "key": "k"},
    }


def _build(tmp_path, raw):
    audio = np.random.default_rng(0).uniform(-0.3, 0.3, 12 * SR).astype(np.float32)
    wav = tmp_path / "x.wav"
    sf.write(wav, audio, SR)
    raw_path = tmp_path / "raw.json"
    raw_path.write_text(json.dumps(raw))
    return make_map(raw_path, wav)


# --- 1. first segment keeps the lead-in -------------------------------------------------


def test_first_segment_starts_at_zero_and_keeps_pickup():
    audio = np.zeros(10 * SR, dtype=np.float32)
    downbeats = [1.0, 3.0, 5.0, 7.0]
    seg = {"start": 0.4, "end": 5.0, "label": "intro"}
    snapped = build_segment(seg, 0, downbeats, [], [], audio, SR)
    first = build_segment(seg, 0, downbeats, [], [], audio, SR, is_first=True)
    assert snapped.start == 1.0  # the old behaviour dropped 1.0 s
    assert first.start == 0.0
    assert first.downbeats == [1.0, 3.0]  # the lead-in is not a bar
    assert first.bars == 2


def test_make_map_first_segment_starts_at_zero_and_segments_tile_the_audio(tmp_path):
    m = _build(tmp_path, _raw(first_downbeat=1.0))
    assert m.segments[0].start == 0.0
    assert m.segments[-1].end == pytest.approx(m.duration)
    for a, b in zip(m.segments, m.segments[1:]):
        assert a.end == b.start  # nothing lost between sections either


def test_offsets_count_from_first_downbeat_not_from_the_lead_in(tmp_path):
    m = _build(tmp_path, _raw(first_downbeat=1.0))
    node = ClipNode(type="clip", id="c", source="a", segment="intro", offset_bars=1)
    start, _ = _clip_bounds(node, m)
    assert start == pytest.approx(1.0 + 2.0)  # first downbeat + 1 bar (2 s at 120 bpm)
    whole, _ = _clip_bounds(ClipNode(type="clip", id="c", source="a", segment="intro"), m)
    assert whole == 0.0  # the clip with no offset includes the lead-in


def test_offset_on_non_first_segment_unchanged(tmp_path):
    m = _build(tmp_path, _raw(first_downbeat=1.0))
    seg = m.segments[1]
    node = ClipNode(type="clip", id="c", source="a", segment="verse", offset_bars=1)
    assert _clip_bounds(node, m)[0] == pytest.approx(seg.start + 2.0)


# --- 2. tempo from the beat grid ---------------------------------------------------------


def test_bpm_from_beats_is_robust_to_missed_and_extra_beats():
    beats = [i * 0.5 for i in range(40)]
    del beats[10]  # a missed beat
    beats.insert(20, beats[19] + 0.1)  # a spurious beat
    assert bpm_from_beats(beats) == pytest.approx(120.0, abs=0.5)
    assert bpm_from_beats([0.0, 0.5]) is None
    assert bpm_from_beats([]) is None


def test_pipeline_copy_matches_shared_function():
    import importlib.util

    pytest.importorskip("modal")
    # load by path: src/analysis/__init__.py has an unrelated import that needs a different sys.path
    spec = importlib.util.spec_from_file_location(
        "pipeline_under_test", Path(__file__).parents[2] / "src" / "analysis" / "pipeline.py")
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    for beats in ([i * 0.41 for i in range(30)], [0.0, 0.5, 1.0], [], [0, 0, 0, 0, 1]):
        assert pipeline.bpm_from_beats(beats) == bpm_from_beats(beats)


def test_make_map_uses_grid_bpm_when_estimate_is_half_time(tmp_path):
    with pytest.warns(UserWarning, match="disagrees with the beat grid"):
        m = _build(tmp_path, _raw(bpm=60.0))
    assert m.bpm == pytest.approx(120.0)
    assert m.bpm_raw == 60.0


def test_make_map_close_estimate_is_replaced_silently(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        m = _build(tmp_path, _raw(bpm=121.0))
    assert m.bpm == pytest.approx(120.0)
    assert m.bpm_raw is None


def test_load_guard_corrects_old_half_time_map_and_warns():
    d = json.loads(FIXTURE_MAP.read_text())
    grid = bpm_from_beats(d["beats"])
    d["bpm"] = grid / 2
    with pytest.warns(UserWarning, match="beat grid"):
        m = parse_recut_map_dict(d)
    assert m.bpm == pytest.approx(grid, abs=0.01)
    assert m.bpm_raw == pytest.approx(grid / 2)


def test_load_guard_leaves_consistent_map_alone():
    d = json.loads(FIXTURE_MAP.read_text())
    d["bpm"] = bpm_from_beats(d["beats"])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        m = parse_recut_map_dict(d)
    assert m.bpm_raw is None


# --- 4. no NaN ----------------------------------------------------------------------------


def test_loudness_of_empty_audio_is_the_floor_not_nan():
    assert loudness_rms_db(np.zeros(0, dtype=np.float32)) == LOUDNESS_FLOOR_DB
    assert loudness_rms_db(np.zeros(100, dtype=np.float32)) == pytest.approx(LOUDNESS_FLOOR_DB)


def test_make_map_has_no_nan_and_no_zero_length_segments(tmp_path):
    # the verse and the 'bridge' both collapse onto one downbeat -> a zero-length segment
    raw = _raw(seg_bounds=((0.0, 5.0, "intro"), (8.9, 9.1, "verse"), (9.1, 9.2, "bridge"),
                           (9.2, 12.0, "silence")))
    m = _build(tmp_path, raw)
    json.dumps(m.model_dump(), allow_nan=False)  # raises on NaN / inf
    assert all(s.duration > 0 for s in m.segments)
    assert [s.index for s in m.segments] == list(range(len(m.segments)))


def test_old_map_with_nan_loudness_still_loads_as_floor():
    d = json.loads(FIXTURE_MAP.read_text())
    d["segments"][0]["loudness_db"] = float("nan")
    m = parse_recut_map_dict(d)
    assert m.segments[0].loudness_db == LOUDNESS_FLOOR_DB
    json.dumps(m.model_dump(), allow_nan=False)


def test_summer_party_example_map_loads(tmp_path):
    example = Path(__file__).parents[2] / "examples" / "summer-party" / "summer-party-map.json"
    m = parse_recut_map(example)  # predates M0: NaN loudness on a zero-length 'silence'
    assert all(s.loudness_db == s.loudness_db for s in m.segments)
    json.dumps(m.model_dump(), allow_nan=False)


# --- 3. recut map --force ---------------------------------------------------------------


def test_map_force_rebuilds_existing_maps(tmp_path, monkeypatch):
    from recut.cli import cmd_map
    from recut.project import Source

    map_dir, raw_dir = tmp_path / "enriched", tmp_path / "raw"
    map_dir.mkdir()
    raw_dir.mkdir()
    sources = {}
    for stem in ("a", "b"):
        (raw_dir / f"{stem}.json").write_text("{}")
        (map_dir / f"{stem}.json").write_text("old")
        sources[stem] = Source(name=stem, audio_path=tmp_path / f"{stem}.mp3",
                               music_map=None, status="ready")
    monkeypatch.setattr("recut.cli.MAP_DIR", map_dir)
    monkeypatch.setattr("recut.cli.RAW_DIR", raw_dir)
    new_map = parse_recut_map(FIXTURE_MAP)

    class A:
        force, stems = False, []

    with patch("recut.cli.load_project_sources", return_value=sources), \
            patch("recut.cli.make_map", return_value=new_map) as mm:
        cmd_map(A())
        assert mm.call_count == 0  # without --force, ready maps are skipped
        A.force = True
        cmd_map(A())
        assert mm.call_count == 2
        mm.reset_mock()
        A.stems = ["b"]
        cmd_map(A())
        assert mm.call_count == 1
    assert (map_dir / "b.json").read_text() != "old"
