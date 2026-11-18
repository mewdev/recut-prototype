"""Song changes (song A whole, then song B) and joins that are not edits.

Regressions 20261118-5hiy and 20261118-ypag (same request kind, both failed it2 the same way:
"second song needs to start earlier ... additional silence which makes the gap too long").
The rejected it2 plans had ~3 s of audible silence at the song change and nothing flagged it
(the silence sat in a `gap` node, which `qc_gap` treats as deliberate). The shipped it3 plans
had 0.5-1.4 s. Meanwhile the song change itself drew `downbeat`, `key_compat`, `bpm_gap`,
`loudness_jump` and `qc_gain_jump`, and the agent added a fake 10 ms gap to silence them.
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from recut.contracts import Plan
from recut.engine import render_plan

REG = Path(__file__).parents[1] / "fixtures" / "regressions"
SR = 22050

# measured on the real sources: where the outgoing song's tail crosses -50 dBFS (the linter read
# 1.1 s of tail before 115.13 s on 5hiy, 0.1 s before 89.32 s on ypag)
TAIL_50DB = {"20261118-5hiy": 114.03, "20261118-ypag": 89.22}
SPLICE_RULES = {"downbeat", "phrase_align", "mid_vocal", "energy_drop", "bpm_gap", "key_compat",
                "loudness_jump", "qc_gain_jump", "qc_tilt_jump"}


def _song(duration: float, quiet_at: float, lead_in: float = 0.3, decay_db_s: float = 30.0) -> np.ndarray:
    """Stand-in for a recorded song: silence for `lead_in`, music at about -18 dBFS RMS, then a
    tail decaying `decay_db_s` (a real recorded tail falls ~20-30 dB/s) that crosses -50 dBFS
    at `quiet_at`."""
    rng = np.random.default_rng(int(duration * 100))
    t = np.arange(int(duration * SR)) / SR
    db = np.full(t.size, -18.0)
    db[t < lead_in] = -120.0
    start = quiet_at - 32.0 / decay_db_s
    tail = t >= start
    db[tail] = np.maximum(-18.0 - decay_db_s * (t[tail] - start), -120.0)
    x = rng.standard_normal(t.size) * 10 ** (db / 20)
    return np.tile(x.astype(np.float32), (2, 1))


@pytest.fixture(scope="module", params=sorted(TAIL_50DB))
def ticket(request, tmp_path_factory):
    tid = request.param
    base = tmp_path_factory.mktemp(tid) / "t"
    shutil.copytree(REG / tid, base)
    (base / "inputs").mkdir()
    for s in ("a", "b"):
        m = json.loads((base / "maps" / f"{s}.json").read_text())
        quiet = TAIL_50DB[tid] if s == "b" else m["duration"] - 0.5
        sf.write(base / "inputs" / f"{s}.wav", _song(m["duration"], quiet).T, SR)
    return tid, base


def _render(base: Path, it: int):
    plan = json.loads((base / "plans" / f"it{it}.json").read_text())
    return render_plan(Plan.model_validate(plan), base, deep_qc=False)[1]


def test_dead_air_at_a_song_change_warns(ticket):
    _, base = ticket
    info = _render(base, 2)  # rejected: tail + a 1.5 s gap + lead-in
    warn = [i for i in info.issues if i.rule == "song_change_gap" and i.severity == "warn"]
    assert len(warn) == 1 and "audible silence" in warn[0].message


def test_shipped_song_change_is_clean(ticket):
    _, base = ticket
    info = _render(base, 3)  # shipped: the next song enters as the tail fades
    sc = [i for i in info.issues if i.rule == "song_change_gap"]
    assert [i.severity for i in sc] == ["info"]  # the number is still reported
    change_splices = {sp.id for sp in info.splices if sp.cross_source}
    assert not [i for i in info.issues if i.splice in change_splices and i.rule in SPLICE_RULES]


def test_contiguous_joins_are_not_judged_as_edits(ticket):
    _, base = ticket
    info = _render(base, 3)
    seg = {s.node_id: s for s in info.segments}
    contiguous = {sp.id for sp in info.splices
                  if seg[sp.from_].source == seg[sp.to].source
                  and abs(seg[sp.from_].src_end - seg[sp.to].src_start) < 1e-3}
    assert contiguous
    assert not [i for i in info.issues if i.splice in contiguous and i.rule in SPLICE_RULES]


def test_a_gain_change_on_a_contiguous_join_is_still_an_edit():
    from recut.contracts.plan import ClipNode
    from recut.contracts.render import RenderSegment, Splice
    from recut.validator.linter import _is_contiguous

    a = ClipNode(id="n1", type="clip", source="a", segment="verse", index=1)
    b = ClipNode(id="n2", type="clip", source="a", segment="chorus", index=1, gain=-6)
    ra = RenderSegment(node_id="n1", source="a", label="verse#1", src_start=0, src_end=10, out_start=0, out_end=10)
    rb = RenderSegment(node_id="n2", source="a", label="chorus#1", src_start=10, src_end=20, out_start=10, out_end=20)
    sp = Splice(id="s1", out_time=10, from_="n1", to="n2", cross_source=False)
    assert not _is_contiguous(a, b, ra, rb, sp)
    assert _is_contiguous(a, b.model_copy(update={"gain": 0}), ra, rb, sp)
