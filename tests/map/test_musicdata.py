"""M2/M3: pace, short-term loudness, key ranges, old maps, enrich commands (synthetic audio)."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from recut import key_essentia, tickets
from recut.map import musicdata
from recut.map.enrich import enrich_map_file
from recut.map.helpers import key_at, pace_at
from recut.map.parser import parse_recut_map
from recut.map.schema import MusicMap

SR = 22050
SUMMER_MAP = Path(__file__).parents[2] / "examples" / "summer-party" / "summer-party-map.json"


def _clicks(times, total_s):
    y = np.zeros(int(total_s * SR), dtype=np.float32)
    n = int(0.01 * SR)
    burst = (np.random.default_rng(0).standard_normal(n) * np.hanning(n)).astype(np.float32)
    for t in times:
        i = int(t * SR)
        y[i: i + n] += 0.8 * burst[: len(y[i: i + n])]
    return y


def _chord(freqs, seconds):
    t = np.arange(int(seconds * SR)) / SR
    y = sum(sum(np.sin(2 * np.pi * f * h * t) / h for h in (1, 2, 3)) for f in freqs)
    return (0.1 * y / len(freqs)).astype(np.float32)


def _tiny_map(duration, downbeats, **kw):
    seg = {
        "index": 0, "segment_name": "verse", "start": 0.0, "end": duration, "duration": duration,
        "bars": len(downbeats), "downbeats": downbeats, "phrases": [], "chords": [],
        "loudness_db": -20.0, "loudness_db_start": -20.0, "loudness_db_end": -20.0,
    }
    ref = {"name": "x", "version": "1"}
    return MusicMap.model_validate({
        "path": "x.wav", "bpm": 120.0, "beats_per_bar": 4, "duration": duration,
        "beats": [i * 0.5 for i in range(int(duration * 2))], "bars": downbeats, "segments": [seg],
        "sources": {"beats": ref, "chords": ref, "structure": ref},
        "meta": {"audio_hash": "h", "generated_at": "t", "map_version": "0.1"}, **kw,
    })


def test_pace_rises_with_onset_density():
    sparse = np.arange(0.25, 20, 1.0)      # 1 click/s
    dense = np.arange(20.25, 40, 0.125)    # 8 clicks/s
    pace = musicdata.compute_pace(_clicks(np.concatenate([sparse, dense]), 40), SR)
    assert len(pace.events_per_min) == 41 and pace.hop_s == 1.0
    early, late = np.mean(pace.events_per_min[3:17]), np.mean(pace.events_per_min[24:38])
    assert late > 3 * early
    assert np.mean(pace.normalized[3:17]) < 0.4 < 0.8 < np.mean(pace.normalized[24:38])
    assert all(0 <= v <= 1 for v in pace.normalized)


def test_pace_silence_is_zero():
    pace = musicdata.compute_pace(np.zeros(5 * SR, dtype=np.float32), SR)
    assert set(pace.events_per_min) == {0.0} and set(pace.normalized) == {0.0}


def test_short_term_loudness_steps_10_lu():
    t = np.arange(20 * SR) / SR
    amp = np.where(t < 10, 0.1, 0.316227766)  # -20 dBFS then -10 dBFS peak
    lufs = musicdata.compute_loudness_short_term((amp * np.sin(2 * np.pi * 997 * t)).astype(np.float32), SR).lufs
    assert lufs[5] == pytest.approx(-23.0, abs=1.0)
    assert np.mean(lufs[14:19]) - np.mean(lufs[2:7]) == pytest.approx(10.0, abs=0.3)


def test_short_term_loudness_silence_is_floored_not_inf():
    lufs = musicdata.compute_loudness_short_term(np.zeros(4 * SR, dtype=np.float32), SR).lufs
    assert lufs == [musicdata.LUFS_FLOOR] * 5


C_MAJ = [261.63, 329.63, 392.0]
A_MAJ = [220.0, 277.18, 329.63]
# I-IV-V-I progressions: a lone triad is ambiguous for a chroma-profile estimate (C-E-G also
# reads as E minor), a progression is what real tracks look like
C_PROG = [C_MAJ, [349.23, 440.0, 523.25], [392.0, 493.88, 587.33], C_MAJ]
A_PROG = [A_MAJ, [293.66, 369.99, 440.0], [329.63, 415.30, 493.88], A_MAJ]


def _prog(chords, seconds):
    cycle = np.concatenate([_chord(c, 2.0) for c in chords])  # 8 s loop, so any window holds whole cycles
    return np.tile(cycle, int(seconds // 8))


@pytest.mark.parametrize("essentia", [False, True])
def test_key_ranges_find_a_key_change(essentia):
    if essentia and not key_essentia.available():
        pytest.skip("essentia not available here")
    audio = np.concatenate([_prog(C_PROG, 32), _prog(A_PROG, 32)])
    downbeats = [2.0 * i for i in range(32)]  # 2 s bars: 16 s per 8-bar window
    ranges, src = musicdata.compute_key_ranges(audio, SR, downbeats, use_essentia=essentia)
    assert src == (musicdata.SRC_KEY_ESSENTIA if essentia else musicdata.SRC_KEY_CHROMA)
    assert len(ranges) == 2
    assert (ranges[0].tonic, ranges[0].mode) == ("C", "major")
    assert (ranges[1].tonic, ranges[1].mode) == ("A", "major")
    assert ranges[0].start == 0.0 and ranges[0].end == ranges[1].start == pytest.approx(32.0)
    assert ranges[1].end == pytest.approx(64.0)


def test_key_ranges_merge_equal_neighbours_and_short_track():
    audio = _prog(C_PROG, 40)
    ranges, _ = musicdata.compute_key_ranges(audio, SR, [2.0 * i for i in range(20)], use_essentia=False)
    assert len(ranges) == 1 and (ranges[0].start, ranges[0].end) == (0.0, pytest.approx(40.0))
    short, _ = musicdata.compute_key_ranges(audio[: 6 * SR], SR, [0.0, 2.0, 4.0], use_essentia=False)
    assert len(short) == 1


def test_key_falls_back_when_essentia_unavailable(monkeypatch):
    monkeypatch.setattr(key_essentia, "available", lambda: False)
    _, src = musicdata.compute_key_ranges(_chord(C_MAJ, 20), SR, [2.0 * i for i in range(10)])
    assert src == musicdata.SRC_KEY_CHROMA


def test_enrich_map_fills_fields_and_segment_pace():
    audio = np.concatenate([_chord(C_MAJ, 20), _chord(A_MAJ, 20)]) + _clicks(np.arange(20.25, 40, 0.25), 40)
    m = _tiny_map(40.0, [2.0 * i for i in range(20)])
    out = musicdata.enrich_map(m, audio, SR)
    assert out.pace and out.loudness_short_term and out.key_ranges
    assert out.analysis_sources["pace"] == "librosa-onsets"
    assert out.analysis_sources["key_ranges"] in (musicdata.SRC_KEY_ESSENTIA, musicdata.SRC_KEY_CHROMA)
    assert out.segments[0].pace is not None and 0 < out.segments[0].pace <= 1
    assert out.instrument_activity is None
    json.dumps(out.model_dump(), allow_nan=False)  # strict JSON, browsers can read it


def test_enrich_keeps_existing_fields_unless_forced():
    audio = _chord(C_MAJ, 20)
    m = musicdata.enrich_map(_tiny_map(20.0, [2.0 * i for i in range(10)]), audio, SR)
    marked = m.model_copy(update={"key_ranges": []})
    assert musicdata.enrich_map(marked, audio, SR).key_ranges == []
    assert musicdata.enrich_map(marked, audio, SR, force=True).key_ranges != []


def test_make_map_time_budget_for_three_minutes():
    audio = _clicks(np.arange(0.5, 180, 0.5), 180) + _chord(C_MAJ, 180)
    m = _tiny_map(180.0, [2.0 * i for i in range(90)])
    t0 = time.time()
    musicdata.enrich_map(m, audio, SR)
    assert time.time() - t0 < 30


def test_old_map_loads_without_new_fields():
    m = parse_recut_map(SUMMER_MAP)
    assert m.pace is None and m.loudness_short_term is None and m.key_ranges is None
    assert m.analysis_sources is None and m.instrument_activity is None
    assert all(s.pace is None and s.drum_activity is None for s in m.segments)
    assert key_at(m, 10.0) == ((m.key.tonic, m.key.mode) if m.key else None)
    assert pace_at(m, 10.0) is None


def test_key_at_and_pace_at_use_the_series():
    m = MusicMap.model_validate({**_tiny_map(40.0, [0.0, 2.0]).model_dump(), **{
        "key_ranges": [
            {"start": 0.0, "end": 20.0, "tonic": "C", "mode": "major"},
            {"start": 20.0, "end": 40.0, "tonic": "A", "mode": "major"},
        ],
        "key": {"tonic": "G", "mode": "minor"},
        "pace": {"hop_s": 1.0, "events_per_min": [0.0, 60.0, 120.0], "normalized": [0.0, 0.5, 1.0]},
    }})
    assert key_at(m, 5.0) == ("C", "major") and key_at(m, 20.0) == ("A", "major")
    assert key_at(m, 99.0) == ("A", "major")
    assert pace_at(m, 1.2) == 0.5 and pace_at(m, 99) == 1.0
    assert pace_at(m, 2.0, normalized=False) == 120.0


def _wav(path, seconds=20):
    sf.write(path, _chord(C_MAJ, seconds), SR)


def test_enrich_map_file_roundtrip(tmp_path):
    audio = tmp_path / "a.wav"
    _wav(audio)
    mp = tmp_path / "a.json"
    mp.write_text(json.dumps(_tiny_map(20.0, [2.0 * i for i in range(10)]).model_dump()))
    assert enrich_map_file(mp, audio) is True
    assert MusicMap.model_validate_json(mp.read_text()).pace is not None
    assert enrich_map_file(mp, audio) is False  # already enriched: untouched
    assert enrich_map_file(mp, audio, force=True) is True


def test_ticket_enrich(tmp_path):
    audio = tmp_path / "song.wav"
    _wav(audio)
    tid = tickets.create_ticket("x", [("song.wav", audio)], root=tmp_path)
    d = tmp_path / tid
    (d / "maps").mkdir()
    (d / "maps" / "a.json").write_text(json.dumps(_tiny_map(20.0, [2.0 * i for i in range(10)]).model_dump()))
    assert tickets.enrich_maps(tid, root=tmp_path) == ["a"]
    assert MusicMap.model_validate_json((d / "maps" / "a.json").read_text()).key_ranges
    assert tickets.enrich_maps(tid, root=tmp_path) == []


def test_cli_map_enrich(tmp_path, monkeypatch, capsys):
    from recut import cli

    audio = tmp_path / "a.wav"
    _wav(audio)
    map_dir = tmp_path / "maps"
    map_dir.mkdir()
    (map_dir / "a.json").write_text(json.dumps(_tiny_map(20.0, [2.0 * i for i in range(10)]).model_dump()))
    source = argparse.Namespace(audio_path=audio, status="ready")
    monkeypatch.setattr(cli, "load_project_sources", lambda: {"a": source, "b": argparse.Namespace(audio_path=audio)})
    monkeypatch.setattr(cli, "MAP_DIR", map_dir)
    cli.cmd_map(argparse.Namespace(force=False, stems=[], enrich=True))
    out = capsys.readouterr().out
    assert "enriched" in out and "skipped b" in out
    assert MusicMap.model_validate_json((map_dir / "a.json").read_text()).pace is not None
