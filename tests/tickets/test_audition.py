"""`recut ticket audition`: short phrase files for the operator to pick an FX by ear."""

import json
import shutil

import pytest
import soundfile as sf

from recut import tickets


@pytest.fixture
def ticket(tmp_path, demo):
    droot, tid = demo
    root = tmp_path / "tickets"
    shutil.copytree(droot / tid, root / tid)
    mp = root / tid / "maps" / "a.json"
    m = json.loads(mp.read_text())
    m["instrument_activity"] = {"vocal": {"hop_s": 0.1, "values": [0.0] * 100,
                                          "ranges": [[1.0, 2.5], [3.0, 12.0]]}}
    mp.write_text(json.dumps(m))
    return root, tid


def test_short_phrases_become_padded_audition_files(ticket):
    root, tid = ticket
    files = tickets.write_auditions(tid, "a", root=root)  # the 9 s range is skipped (> 4 s)
    assert [f.name for f in files] == ["a_vocal_1.0-2.5.wav"]
    assert files[0].parent.name == "audition"
    assert sf.info(str(files[0])).duration == pytest.approx(1.5 + 2 * 0.3, abs=0.01)


def test_stem_file_is_preferred_over_the_mix(ticket):
    root, tid = ticket
    stem = tickets.stems_dir(tid, "a", root) / "vocals.flac"
    stem.parent.mkdir(parents=True)
    x, sr = sf.read(str(root / tid / tickets.sources(tid, root)["a"]["file"]), frames=44100 * 5)
    sf.write(str(stem), x * 0, sr)  # silent stand-in: the audition must come from it
    f = tickets.write_auditions(tid, "a", root=root)[0]
    assert abs(sf.read(str(f))[0]).max() == 0


def test_missing_activity_says_how_to_get_it(demo):
    root, tid = demo
    with pytest.raises(ValueError, match="recut ticket enrich"):
        tickets.write_auditions(tid, "a", stem="drum", root=root)
