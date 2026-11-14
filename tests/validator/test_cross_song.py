"""A5: cross-song linter rules (downbeat, bpm_gap, key_compat, loudness_jump), one pass + one fail each."""

import json
from pathlib import Path

import numpy as np

from recut.audio import Audio
from recut.contracts import Plan
from recut.contracts.render import RenderSegment, Splice
from recut.map.schema import KeySignature, MusicMap
from recut.validator.camelot import camelot, keys_compatible
from recut.validator.linter import lint_plan

MAP = json.loads((Path(__file__).parents[2] / "examples/summer-party/summer-party-map.json").read_text())
SR = 22050
BARS = [10.0, 12.0, 14.0, 16.0]


def mmap(bpm=120.0, key=("A", "minor"), bars=BARS) -> MusicMap:
    m = MusicMap.model_validate(MAP).model_copy(update={"bpm": bpm, "bars": bars})
    m.key = KeySignature(tonic=key[0], mode=key[1]) if key else None
    return m


def tone(db, seconds=30.0) -> Audio:
    t = np.arange(int(seconds * SR)) / SR
    x = (10 ** (db / 20) * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    return Audio(np.stack([x, x]), SR)


def lint(a=None, b=None, *, out_end=14.0, in_start=12.0, overlap_ms=0.0, cross=True, audio=None,
         gain_b=0.0):
    maps = {"a": a or mmap(), "b": b or mmap()}
    src_b = "b" if cross else "a"
    plan = Plan.model_validate({
        "version": 2,
        "sources": {"a": {"file": "a.wav", "map": "a.json"}, "b": {"file": "b.wav", "map": "b.json"}},
        "tracks": [{"id": "main", "clips": [
            {"id": "n1", "type": "clip", "source": "a", "segment": "verse", "index": 1},
            {"id": "n2", "type": "clip", "source": src_b, "segment": "chorus", "index": 1, "gain": gain_b}]}],
    })
    segs = [RenderSegment(node_id="n1", source="a", label="verse#1", src_start=10, src_end=out_end,
                          out_start=0, out_end=out_end - 10),
            RenderSegment(node_id="n2", source=src_b, label="chorus#1", src_start=in_start,
                          src_end=in_start + 8, out_start=out_end - 10, out_end=out_end - 2)]
    sp = [Splice.model_validate({"id": "s1", "out_time": out_end - 10, "from": "n1", "to": "n2",
                                 "cross_source": cross, "overlap_ms": overlap_ms})]
    issues = lint_plan(plan, maps, segs, sp, audio=audio)
    return {i.rule: i for i in issues if i.rule in {"downbeat", "bpm_gap", "key_compat", "loudness_jump"}}


# ---- downbeat ---------------------------------------------------------------------------

def test_downbeat_passes_on_bars_with_and_without_overlap():
    assert "downbeat" not in lint()
    assert "downbeat" not in lint(out_end=14.5, overlap_ms=500)  # outgoing side measured at the overlap start


def test_downbeat_errors_off_grid_on_every_splice_kind():
    for cross in (True, False):
        r = lint(out_end=14.25, cross=cross)
        assert r["downbeat"].severity == "error" and r["downbeat"].splice == "s1"
        assert "outgoing" in r["downbeat"].message
    assert "incoming" in lint(in_start=12.1)["downbeat"].message
    assert "downbeat" in lint(out_end=14.5, overlap_ms=200)  # overlap moves the outgoing join off the bar
    assert "downbeat" not in lint(overlap_ms=30)  # a short click-cover overlap doesn't shift the join


# ---- bpm_gap ----------------------------------------------------------------------------

def test_bpm_gap_passes_within_3_percent_and_for_double_time():
    assert "bpm_gap" not in lint(b=mmap(bpm=123.0))
    assert "bpm_gap" not in lint(b=mmap(bpm=240.0))
    assert "bpm_gap" not in lint(b=mmap(bpm=60.0))


def test_bpm_gap_warns_and_skips_same_source():
    r = lint(a=mmap(116), b=mmap(124))
    assert r["bpm_gap"].severity == "warn" and r["bpm_gap"].splice == "s1"
    assert "bpm_gap" not in lint(a=mmap(116), cross=False)


# ---- key_compat -------------------------------------------------------------------------

def test_camelot_helper():
    assert camelot("A", "minor") == (8, "A") and camelot("C", "major") == (8, "B")
    assert camelot("F#", "minor") == (11, "A") and camelot("Gb", "minor") == (11, "A")
    assert camelot("Bb", "major") == (6, "B") and camelot("A#", "major") == (6, "B")
    assert camelot("H", "major") is None and camelot("C", "dorian") is None
    assert keys_compatible((8, "A"), (8, "B")) and keys_compatible((12, "A"), (1, "A"))
    assert keys_compatible((8, "A"), (9, "A")) and not keys_compatible((8, "A"), (10, "A"))
    assert not keys_compatible((8, "A"), (9, "B"))


def test_key_compat_passes_same_relative_adjacent_and_missing():
    assert "key_compat" not in lint()
    assert "key_compat" not in lint(b=mmap(key=("C", "major")))   # relative
    assert "key_compat" not in lint(b=mmap(key=("E", "minor")))   # +1 Camelot
    assert "key_compat" not in lint(b=mmap(key=None))


def test_key_compat_warns_on_distant_keys():
    r = lint(b=mmap(key=("F#", "minor")))
    assert r["key_compat"].severity == "warn" and r["key_compat"].splice == "s1"
    assert "key_compat" not in lint(b=mmap(key=("F#", "minor")), cross=False)


# ---- loudness_jump ----------------------------------------------------------------------

def test_loudness_jump_passes_when_matched_or_gain_compensates():
    audio = {"a": tone(-20), "b": tone(-20)}
    assert "loudness_jump" not in lint(audio=audio)
    assert "loudness_jump" not in lint(audio={"a": tone(-20), "b": tone(-26)}, gain_b=6)


def test_loudness_jump_warns_on_a_jump_over_3_db():
    r = lint(audio={"a": tone(-20), "b": tone(-27)})
    assert r["loudness_jump"].severity == "warn" and r["loudness_jump"].splice == "s1"
    assert "loudness_jump" not in lint(audio={"a": tone(-20), "b": tone(-27)}, cross=False)
    assert "loudness_jump" not in lint()  # no audio: rule is skipped


def test_key_compat_uses_the_key_at_the_join_when_the_song_modulates():
    """Global key says compatible, but source b has modulated to a distant key where it's cut in."""
    from recut.map.schema import KeyRange

    b = mmap(key=("A", "minor"))  # global: same as a
    b.key_ranges = [KeyRange(start=0.0, end=11.0, tonic="A", mode="minor"),
                    KeyRange(start=11.0, end=60.0, tonic="F#", mode="minor")]
    r = lint(b=b, in_start=12.0)
    assert "key_compat" in r and "F#" in r["key_compat"].message
    assert "key_compat" not in lint(b=b, in_start=10.0)  # cut in before the modulation
