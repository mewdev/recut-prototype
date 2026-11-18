"""M1: stem activity curves, ranges, map fields, mocked Modal client, enrich path. No network, no GPU."""

import importlib.util
import json
import subprocess
import types
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from recut import analysis_client, sync, tickets
from recut.map import activity
from recut.map.activity import (
    activity_at,
    activity_ranges,
    bar_seconds,
    curves_from_stems_dir,
    stem_activity,
)
from recut.map.enrich import enrich_map_file
from recut.map.make_map import run as make_map
from recut.map.parser import parse_recut_map, parse_recut_map_dict
from recut.map.schema import MusicMap

SR = 44100
FIXTURE_MAP = Path(__file__).parents[1] / "fixtures" / "sample-map.json"


def tone(seconds, amp=0.3, sr=SR, f=220.0):
    t = np.arange(int(seconds * sr)) / sr
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


def burst_signal(total=10.0, start=3.0, end=6.0, sr=SR):
    x = np.zeros(int(total * sr), dtype=np.float32)
    a, b = int(start * sr), int(end * sr)
    x[a:b] = tone(end - start, sr=sr)
    return x


# ---- curve maths ---------------------------------------------------------------------------


def test_silence_is_all_zeros_without_nan():
    v = stem_activity(np.zeros(5 * SR, dtype=np.float32), SR)
    assert len(v) == 50 and set(v) == {0.0}


def test_sparse_stem_uses_its_peak_as_reference_but_bleed_stays_zero():
    # 3 s of audible tone in 100 s: the 95th percentile is silence, so the peak is the reference
    v = np.array(stem_activity(burst_signal(100.0, 10.0, 13.0), SR))
    assert v[115] == 1.0 and v[:90].max() == 0.0
    # the same shape at -45 dBFS is bleed, not an instrument
    quiet = burst_signal(100.0, 10.0, 13.0) * (10 ** (-45 / 20) / 0.3)
    assert set(stem_activity(quiet, SR)) == {0.0}


def test_stem_quieter_than_the_floor_is_all_zeros():
    # -70 dBFS sine: its own 95th percentile is under the -50 dBFS floor
    assert set(stem_activity(tone(3, amp=10 ** (-70 / 20) * 1.414), SR)) == {0.0}


def test_empty_input_gives_no_values():
    assert stem_activity(np.zeros(0, dtype=np.float32), SR) == []


def test_constant_tone_sits_at_one_everywhere():
    v = np.array(stem_activity(tone(4), SR))
    assert len(v) == 40 and np.all(v == 1.0)  # its own 95th percentile is its level


def test_level_is_relative_to_the_stems_own_95th_percentile_and_the_floor():
    # 0.3 for 8 s, then a section 20 dB lower (0.03): relative to the stem's loud level
    x = np.concatenate([tone(8, amp=0.3), tone(2, amp=0.03)])
    v = np.array(stem_activity(x, SR))
    assert v[:70].min() == 1.0
    # top = a 0.3 sine = -13.5 dBFS; the quiet part is -33.5 dBFS: (-33.5 + 50) / (-13.5 + 50)
    top_db = 20 * np.log10(0.3 / np.sqrt(2))
    assert v[-5:].mean() == pytest.approx((top_db - 20 + 50) / (top_db + 50), abs=0.01)


def test_values_stay_in_unit_range_for_loud_noise():
    x = np.random.default_rng(1).uniform(-1, 1, 6 * SR).astype(np.float32)
    v = np.array(stem_activity(x, SR))
    assert v.min() >= 0.0 and v.max() <= 1.0 and not np.isnan(v).any()


def test_stereo_input_and_partial_last_hop():
    x = np.stack([tone(1.05), tone(1.05)])
    v = stem_activity(x, SR)
    assert len(v) == 11  # 10 full hops + a 50 ms tail


def test_smoothing_spreads_one_loud_hop_over_300_ms():
    x = np.zeros(2 * SR, dtype=np.float32)
    hop = SR // 10
    x[10 * hop: 11 * hop] = tone(0.1)  # one loud 100 ms hop
    raw = stem_activity(x, SR, smooth_s=0.1)
    smooth = stem_activity(x, SR)
    assert raw[10] == 1.0 and raw[9] == 0.0 and raw[11] == 0.0
    assert [smooth[9], smooth[10], smooth[11]] == pytest.approx([1 / 3] * 3, abs=1e-3)
    assert smooth[8] == 0.0 and smooth[12] == 0.0


def test_burst_gives_one_range_at_the_burst():
    v = stem_activity(burst_signal(), SR)  # 3 s of tone in 10 s of silence
    (a, b), = activity_ranges(v, 0.1, min_len_s=2.0)
    assert a == pytest.approx(3.0, abs=0.2) and b == pytest.approx(6.0, abs=0.2)


def test_ranges_need_at_least_the_minimum_length():
    v = stem_activity(burst_signal(), SR)
    assert activity_ranges(v, 0.1, min_len_s=2.0)  # 3 s burst, bar of 2 s: kept
    assert activity_ranges(v, 0.1, min_len_s=4.0) == []  # 3 s burst, bar of 4 s: dropped


def test_ranges_run_to_the_end_and_use_the_threshold():
    assert activity_ranges([0, 0.5, 0.5, 0.5], 1.0, 2.0) == [(1.0, 4.0)]
    assert activity_ranges([0.25, 0.25, 0.25], 1.0, 1.0) == []  # strictly above 0.25
    assert activity_ranges([], 0.1, 1.0) == []


def test_bar_seconds_prefers_downbeats_then_beats_then_bpm_then_fallback():
    assert bar_seconds(bars=[0, 2, 4, 6.1], beats=None, bpm=100) == pytest.approx(2.0)
    assert bar_seconds(bars=[0.0], beats=[0, 0.5, 1.0, 1.5], bpm=100, beats_per_bar=3) == pytest.approx(1.5)
    assert bar_seconds(bars=[], beats=[], bpm=120, beats_per_bar=4) == pytest.approx(2.0)
    assert bar_seconds(bars=[], beats=[], bpm=0) == activity.FALLBACK_BAR_S
    assert bar_seconds() == activity.FALLBACK_BAR_S


def test_modal_copy_of_the_maths_matches_the_local_module():
    pytest.importorskip("modal")
    spec = importlib.util.spec_from_file_location(
        "pipeline_under_test", Path(__file__).parents[2] / "src" / "analysis" / "pipeline.py")
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    rng = np.random.default_rng(3)
    signals = [burst_signal(), np.zeros(SR, dtype=np.float32), rng.uniform(-1, 1, 3 * SR).astype(np.float32),
               np.stack([tone(2), tone(2, amp=0.01)]), np.zeros(0, dtype=np.float32)]
    for x in signals:
        assert pipeline.stem_activity(x, SR) == stem_activity(x, SR)
    v = stem_activity(burst_signal(), SR)
    assert pipeline.activity_ranges(v, 0.1, 2.0) == [list(r) for r in activity_ranges(v, 0.1, 2.0)]


# ---- map fields ----------------------------------------------------------------------------


def _raw_with_activity(curves=None):
    beats = [round(1.0 + 0.5 * i, 3) for i in range(20)]  # 120 bpm: a bar is 2 s
    raw = {
        "path": "x.wav", "bpm": 120.0, "beats_per_bar": 4, "beats": beats, "downbeats": beats[::4],
        "segments": [{"start": 0.0, "end": 5.0, "label": "intro"}, {"start": 5.0, "end": 9.0, "label": "verse"},
                     {"start": 9.0, "end": 12.0, "label": "silence"}],
        "chords": [], "key": "C major",
        "_sources": {"beats": "madmom", "chords": "c", "structure": "s", "key": "k"},
    }
    if curves is not None:
        raw["_activity"] = {"hop_s": 0.1, "curves": curves}
        raw["_sources"]["instrument_activity"] = "demucs-htdemucs"
    return raw


def _curves(drums_span=(5.0, 9.0), vocal_span=(1.0, 4.0), n=120):
    def on(span):
        return [1.0 if span[0] <= i * 0.1 < span[1] else 0.0 for i in range(n)]
    return {"drums": on(drums_span), "vocals": on(vocal_span), "bass": [0.0] * n, "other": [0.5] * n}


def _build(tmp_path, raw):
    wav = tmp_path / "x.wav"
    sf.write(wav, np.random.default_rng(0).uniform(-0.3, 0.3, 12 * 22050).astype(np.float32), 22050)
    p = tmp_path / "raw.json"
    p.write_text(json.dumps(raw))
    return make_map(p, wav)


def test_make_map_fills_activity_from_the_raw_curves(tmp_path):
    m = _build(tmp_path, _raw_with_activity(_curves()))
    ia = m.instrument_activity
    assert m.analysis_sources["instrument_activity"] == "demucs-htdemucs"
    assert ia.drum.hop_s == 0.1 and len(ia.drum.values) == 120
    assert ia.drum.ranges == [(5.0, 9.0)] and ia.vocal.ranges == [(1.0, 4.0)]  # both >= 1 bar (2 s)
    assert ia.bass.ranges == [] and ia.other.ranges == [(0.0, 12.0)]
    intro, verse, _ = m.segments
    assert verse.drum_activity == pytest.approx(1.0) and intro.drum_activity == pytest.approx(0.0)
    assert intro.vocal_activity == pytest.approx(0.6) and verse.vocal_activity == pytest.approx(0.0)
    json.dumps(m.model_dump(), allow_nan=False)


def test_short_bursts_below_one_bar_are_not_ranges(tmp_path):
    m = _build(tmp_path, _raw_with_activity(_curves(vocal_span=(1.0, 2.5))))  # 1.5 s < a 2 s bar
    assert m.instrument_activity.vocal.ranges == []


def test_make_map_without_stems_has_no_activity_and_is_unchanged(tmp_path):
    m = _build(tmp_path, _raw_with_activity(None))
    assert m.instrument_activity is None and "instrument_activity" not in m.analysis_sources
    assert all(s.drum_activity is None and s.vocal_activity is None for s in m.segments)


def test_schema_round_trip_and_activity_at(tmp_path):
    m = _build(tmp_path, _raw_with_activity(_curves()))
    again = MusicMap.model_validate_json(json.dumps(m.model_dump()))
    assert again == m
    assert activity_at(again, "drum", 6.0) == 1.0 and activity_at(again, "drum", 2.0) == 0.0
    assert activity_at(again, "vocal", 999.0) == 0.0  # clamps to the last sample
    assert activity_at(parse_recut_map(FIXTURE_MAP), "drum", 1.0) is None


def test_old_maps_without_activity_still_load():
    m = parse_recut_map(FIXTURE_MAP)
    assert m.instrument_activity is None
    d = json.loads(FIXTURE_MAP.read_text())
    d["instrument_activity"] = {"drum": {"values": [0.1, 0.2]}}  # shape from the frozen schema
    assert parse_recut_map_dict(d).instrument_activity.drum.ranges == []


# ---- mocked Modal client -------------------------------------------------------------------


class _Call:
    def __init__(self, value=None, error=None):
        self.value, self.error = value, error

    def get(self):
        if self.error:
            raise self.error
        return self.value


class _Fn:
    def __init__(self, value=None, error=None, spawn_error=None):
        self.value, self.error, self.spawn_error = value, error, spawn_error

    def spawn(self, *args, **kwargs):
        self.kwargs = kwargs
        if self.spawn_error:
            raise self.spawn_error
        value = self.value
        if isinstance(value, dict) and "stems" in value and not kwargs.get("return_stems"):
            value = {**value, "stems": {}}  # like run_stems: audio only on request
        return _Call(value, self.error)


def _fake_modal(monkeypatch, stems: _Fn):
    beats = {"bpm": 120.0, "beats_per_bar": 4, "beats": [0.5, 1.0], "downbeats": [0.5]}
    fns = {"run_beats": _Fn(beats), "run_chords": _Fn({"chords": []}),
           "run_structure": _Fn({"segments": []}), "run_key": _Fn({"key": "C major"}),
           "run_stems": stems}
    fake = types.SimpleNamespace(Function=types.SimpleNamespace(from_name=lambda app, name: fns[name]))
    monkeypatch.setitem(__import__("sys").modules, "modal", fake)


def _stem_result():
    flac = {}
    for name in activity.STEM_NAMES:
        path = Path(pytest.importorskip("tempfile").mkdtemp()) / f"{name}.flac"
        sf.write(path, tone(1.0), SR, format="FLAC")
        flac[name] = path.read_bytes()
    return {"stems": flac, "activity": {n: stem_activity(tone(1.0), SR) for n in flac}, "hop_s": 0.1,
            "ranges": {}, "sample_rate": SR, "model": "demucs-htdemucs"}


def test_analyze_raw_by_default_keeps_curves_but_no_stem_audio(tmp_path, monkeypatch):
    monkeypatch.delenv("RECUT_KEEP_STEMS", raising=False)
    fn = _Fn(_stem_result())
    _fake_modal(monkeypatch, fn)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    stems = tmp_path / "stems" / "a"
    raw = analysis_client.analyze_raw(audio, log=lambda *_: None, stems_dir=stems)
    assert fn.kwargs == {"return_stems": False}  # Modal doesn't even send the audio back
    assert not stems.exists()
    assert set(raw["_activity"]["curves"]) == set(activity.STEM_NAMES)


@pytest.mark.parametrize("value,expected", [("1", True), ("yes", True), ("0", False), ("", False)])
def test_keep_stems_env(monkeypatch, value, expected):
    monkeypatch.setenv("RECUT_KEEP_STEMS", value)
    assert analysis_client.keep_stems() is expected


def test_analyze_raw_spawns_stems_saves_flac_and_returns_only_curves(tmp_path, monkeypatch):
    monkeypatch.setenv("RECUT_KEEP_STEMS", "1")
    _fake_modal(monkeypatch, _Fn(_stem_result()))
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    stems = tmp_path / "stems" / "a"
    raw = analysis_client.analyze_raw(audio, log=lambda *_: None, stems_dir=stems)
    assert sorted(p.name for p in stems.glob("*.flac")) == ["bass.flac", "drums.flac", "other.flac", "vocals.flac"]
    assert set(raw["_activity"]["curves"]) == set(activity.STEM_NAMES)
    assert raw["_sources"]["instrument_activity"] == "demucs-htdemucs"
    json.dumps(raw)  # no bytes leak into the raw JSON


@pytest.mark.parametrize("stems", [_Fn(error=RuntimeError("CUDA OOM")), _Fn(spawn_error=RuntimeError("not deployed"))])
def test_stem_failure_keeps_the_rest_of_the_analysis(tmp_path, monkeypatch, stems):
    _fake_modal(monkeypatch, stems)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    logs = []
    raw = analysis_client.analyze_raw(audio, log=logs.append, stems_dir=tmp_path / "stems")
    assert raw["bpm"] == 120.0 and raw["key"] == "C major"
    assert "_activity" not in raw and "instrument_activity" not in raw["_sources"]
    assert any("stem" in str(line) for line in logs)  # the warning
    assert not (tmp_path / "stems").exists()


# ---- enrich path (existing maps) ------------------------------------------------------------


def _wav(path, seconds=12):
    sf.write(path, tone(seconds, sr=22050), 22050)


def _old_map(tmp_path, name="a.json", m2=False):
    """A map from before M1 (and, unless `m2`, before M2: no pace / loudness / key ranges)."""
    m = _build(tmp_path, _raw_with_activity(None)).model_dump()
    assert m["instrument_activity"] is None
    if not m2:
        m.update(pace=None, loudness_short_term=None, key_ranges=None, analysis_sources=None)
    p = tmp_path / name
    p.write_text(json.dumps(m))
    return p


def _save_stems(stems_dir, curves_signal):
    stems_dir.mkdir(parents=True)
    for name in activity.STEM_NAMES:
        sf.write(stems_dir / f"{name}.flac", curves_signal(name), SR, format="FLAC")


def test_enrich_reuses_saved_stems_without_calling_modal(tmp_path):
    audio = tmp_path / "a.wav"
    _wav(audio)
    mp = _old_map(tmp_path)
    stems = tmp_path / "stems" / "a"
    _save_stems(stems, lambda n: burst_signal(12.0, 5.0, 9.0) if n == "drums" else np.zeros(12 * SR, np.float32))

    def boom(*_):
        raise AssertionError("Modal must not be called when stems are saved")

    assert enrich_map_file(mp, audio, stems_dir=stems, fetch_stems=boom) is True
    m = MusicMap.model_validate_json(mp.read_text())
    assert m.pace is not None and m.analysis_sources["instrument_activity"] == "demucs-htdemucs"
    assert m.instrument_activity.drum.ranges and m.instrument_activity.vocal.ranges == []
    assert m.segments[1].drum_activity > 0.9 and m.segments[0].drum_activity < 0.1
    assert enrich_map_file(mp, audio, stems_dir=stems, fetch_stems=boom) is False  # nothing missing


def test_enrich_calls_modal_for_stems_only_and_keeps_saved_files(tmp_path):
    audio = tmp_path / "a.wav"
    _wav(audio)
    mp = _old_map(tmp_path)
    calls = []

    def fetch(audio_path, stems_dir):
        calls.append((audio_path, stems_dir))
        return {"hop_s": 0.1, "curves": _curves()}

    assert enrich_map_file(mp, audio, stems_dir=tmp_path / "stems" / "a", fetch_stems=fetch) is True
    assert len(calls) == 1
    assert MusicMap.model_validate_json(mp.read_text()).instrument_activity.drum.ranges == [(5.0, 9.0)]


def test_enrich_without_stems_dir_never_touches_activity(tmp_path):
    audio = tmp_path / "a.wav"
    _wav(audio)
    mp = _old_map(tmp_path)
    assert enrich_map_file(mp, audio) is True
    assert MusicMap.model_validate_json(mp.read_text()).instrument_activity is None


def test_failed_stem_fetch_still_enriches_m2_and_leaves_activity_missing(tmp_path):
    audio = tmp_path / "a.wav"
    _wav(audio)
    mp = _old_map(tmp_path)

    def fail(*_):
        raise RuntimeError("no modal token")

    assert enrich_map_file(mp, audio, stems_dir=tmp_path / "s", fetch_stems=fail) is True  # M2 added
    m = MusicMap.model_validate_json(mp.read_text())
    assert m.pace is not None and m.instrument_activity is None
    # only activity missing now, and still unobtainable: file untouched, reports no change
    before = mp.read_text()
    assert enrich_map_file(mp, audio, stems_dir=tmp_path / "s", fetch_stems=fail) is False
    assert mp.read_text() == before


def test_corrupt_saved_stems_fall_back_to_modal(tmp_path):
    stems = tmp_path / "s"
    stems.mkdir()
    for name in activity.STEM_NAMES:
        (stems / f"{name}.flac").write_bytes(b"not flac")
    from recut.map.enrich import get_activity_curves

    got = get_activity_curves(tmp_path / "a.wav", stems, lambda *_: {"hop_s": 0.1, "curves": {"drums": [0.0]}},
                              log=lambda *_: None)
    assert got == ({"drums": [0.0]}, 0.1)


def test_curves_from_stems_dir_needs_all_four(tmp_path):
    tmp_path.joinpath("d").mkdir()
    sf.write(tmp_path / "d" / "drums.flac", tone(1.0), SR, format="FLAC")
    assert curves_from_stems_dir(tmp_path / "d") is None
    assert curves_from_stems_dir(tmp_path / "missing") is None


def test_ticket_enrich_with_activity_uses_ticket_stems_dir(tmp_path):
    audio = tmp_path / "song.wav"
    _wav(audio)
    tid = tickets.create_ticket("x", [("song.wav", audio)], root=tmp_path)
    d = tmp_path / tid
    (d / "maps").mkdir()
    (d / "maps" / "a.json").write_text(_old_map(tmp_path).read_text())
    assert tickets.stems_dir(tid, "a", tmp_path) == d / "stems" / "a"
    seen = []

    def fetch(audio_path, stems_dir):
        seen.append(stems_dir)
        return {"hop_s": 0.1, "curves": _curves()}

    assert tickets.enrich_maps(tid, root=tmp_path, activity=True, fetch_stems=fetch) == ["a"]
    assert seen == [d / "stems" / "a"]
    assert MusicMap.model_validate_json((d / "maps" / "a.json").read_text()).instrument_activity is not None
    assert tickets.enrich_maps(tid, root=tmp_path, activity=True, fetch_stems=fetch) == []


def test_ensure_maps_default_saves_stems_under_the_ticket(tmp_path, monkeypatch):
    audio = tmp_path / "song.wav"
    _wav(audio)
    tid = tickets.create_ticket("x", [("song.wav", audio)], root=tmp_path)
    got = {}

    def fake(audio_path, stems_dir=None):
        got["stems_dir"] = stems_dir
        return MusicMap.model_validate_json(_old_map(tmp_path).read_text())

    monkeypatch.setattr(analysis_client, "analyze_to_map", fake)
    assert tickets.ensure_maps(tid, root=tmp_path) == ["a"]
    assert got["stems_dir"] == tmp_path / tid / "stems" / "a"


def test_cli_enrich_passes_activity_flag(monkeypatch):
    import sys

    from recut import cli

    seen = []
    monkeypatch.setattr(tickets, "enrich_maps", lambda tid, force=False, activity=False: seen.append(activity) or [])
    monkeypatch.setattr(cli, "load_project_sources", lambda: {})
    monkeypatch.setattr(cli, "_enrich_sources", lambda sources, stems, activity=False: seen.append(("map", activity)))
    for argv in (["ticket", "enrich", "t1"], ["ticket", "enrich", "t1", "--no-activity"],
                 ["map", "--enrich"], ["map", "--enrich", "--no-activity"]):
        monkeypatch.setattr(sys, "argv", ["recut", *argv])
        cli.main()
    assert seen == [True, False, ("map", True), ("map", False)]


# ---- stems are audio: never committed -------------------------------------------------------


def test_flac_stems_are_git_ignored_in_the_data_repo(tmp_path):
    (tmp_path / ".gitignore").write_text(sync.GITIGNORE)
    stem = tmp_path / "tickets" / "t1" / "stems" / "a" / "drums.flac"
    stem.parent.mkdir(parents=True)
    stem.write_bytes(b"fLaC")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    r = subprocess.run(["git", "-C", str(tmp_path), "check-ignore", str(stem)], capture_output=True, text=True)
    assert r.returncode == 0, "stems/*.flac must be ignored by the data repo"
