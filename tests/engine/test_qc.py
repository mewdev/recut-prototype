"""Q1: audio QC. Synthetic audio per rule, with the Essentia backend and the numpy/scipy fallback."""

import json

import numpy as np
import pyloudnorm as pyln
import pytest
from scipy import signal

from recut import qc, qc_essentia, tickets
from recut.audio import Audio
from recut.contracts.render import RenderSegment, Splice
from recut.devices import limit
from recut.qc import RenderInfoQC

SR = 44100
RNG = np.random.default_rng(7)


@pytest.fixture(params=["basic", "essentia"])
def backend(request, monkeypatch):
    if request.param == "basic":
        monkeypatch.setenv("RECUT_QC_ESSENTIA", "0")
    else:
        pytest.importorskip("essentia")
        monkeypatch.setenv("RECUT_QC_ESSENTIA", "1")
    return request.param


def music(sec: float, amp: float = 0.3) -> np.ndarray:
    """Stereo tones plus a little noise, (2, n) float32."""
    t = np.arange(int(sec * SR)) / SR
    base = amp * np.sin(2 * np.pi * 220 * t) + 0.3 * amp * np.sin(2 * np.pi * 1230 * t)
    return np.stack([base + 0.02 * RNG.standard_normal(t.size) * amp / 0.3 for _ in range(2)]).astype(np.float32)


def info(x: np.ndarray, splices=(), segments=(), limiter=False) -> RenderInfoQC:
    return RenderInfoQC(duration_s=x.shape[-1] / SR, segments=list(segments), splices=list(splices),
                      peak_dbfs=-1.0, limiter_applied=limiter)


def hard_cut(t: float, same_source_contiguous: bool = False) -> tuple[list[Splice], list[RenderSegment]]:
    segs = [RenderSegment(node_id="n1", source="a", label="x#1", src_start=0, src_end=10,
                          out_start=0, out_end=t),
            RenderSegment(node_id="n2", source="a" if same_source_contiguous else "b", label="y#1",
                          src_start=10 if same_source_contiguous else 30, src_end=20,
                          out_start=t, out_end=t + 4)]
    return [Splice(id="s1", out_time=t, from_="n1", to="n2", cross_source=not same_source_contiguous)], segs


def run(x, **kw):
    sp, seg = kw.pop("cut", ([], []))
    inf = info(x, sp, seg, kw.pop("limiter", False))
    return qc.run_qc(Audio(x, SR), inf, **kw), inf


def rules(issues, sev=None):
    return {i.rule for i in issues if sev is None or i.severity == sev}


# ---- loudness, limiting, peaks ------------------------------------------------------------


def test_integrated_lufs_matches_pyloudnorm():
    x = music(20, 0.3) + 0.2 * np.sin(2 * np.pi * 80 * np.arange(20 * SR) / SR).astype(np.float32)
    ours = qc.integrated_lufs(x, SR)
    assert ours == pytest.approx(pyln.Meter(SR).integrated_loudness(x.T), abs=0.05)


def test_loudness_warns_outside_range_only(backend):
    quiet = run(music(6, 0.01))[0]
    loud = run(np.clip(music(6, 1.4), -1, 1))[0]
    assert "qc_loudness" in rules(quiet) and "qc_loudness" in rules(loud)
    ok = next(a for a in (0.2, 0.25, 0.3, 0.35, 0.4)
              if -16 <= (qc.integrated_lufs(music(6, a), SR) or -99) <= -9)
    assert "qc_loudness" not in rules(run(music(6, ok))[0])


def test_limiting_warns_on_deep_gain_reduction_only(backend):
    pre = music(4, 0.9) * 2.5
    out = limit(pre.copy(), SR, -1.0)
    issues, inf = run(out, pre_master=pre, limiter=True)
    assert "qc_limiting" in rules(issues) and inf.qc["max_gain_reduction_db"] > 3
    mild = music(4, 0.3) * 1.2
    issues, inf = run(limit(mild.copy(), SR, -1.0), pre_master=mild, limiter=True)
    assert "qc_limiting" not in rules(issues)


def test_true_peak_sees_intersample_peaks(backend):
    n = np.arange(SR)
    # sr/4 sine at 45 degrees: every sample is +-0.707, the reconstructed peak is 1.0
    x = np.stack([np.sin(2 * np.pi * (SR / 4) * n / SR + np.pi / 4)] * 2).astype(np.float32)
    issues, inf = run(x)
    assert inf.qc["sample_peak_dbfs"] == pytest.approx(-3.0, abs=0.1)
    assert inf.qc["true_peak_dbtp"] == pytest.approx(0.0, abs=0.15)
    assert "qc_true_peak" in rules(issues)
    quiet, qinf = run(x * 0.5)
    assert qinf.qc["true_peak_dbtp"] < -5 and "qc_true_peak" not in rules(quiet)


def test_true_peak_agrees_with_full_oversampling():
    x = music(3, 0.9)
    _, tp = qc.true_peak(x)
    full = float(np.abs(signal.resample_poly(x, 4, 1, axis=-1)).max())
    assert tp == pytest.approx(full, rel=0.02)


# ---- clipping, DC, phase ----------------------------------------------------------------


def test_clipping_is_an_error(backend):
    x = music(4, 0.3)
    assert "qc_clipping" not in rules(run(x)[0])
    x[:, 2 * SR: 2 * SR + 40] = 1.0  # a flat run at full scale
    issues, _ = run(x)
    hit = [i for i in issues if i.rule == "qc_clipping"]
    assert hit and hit[0].severity == "error"


def test_dc_and_phase(backend):
    x = music(3)
    assert not rules(run(x)[0]) & {"qc_dc", "qc_phase"}
    assert "qc_dc" in rules(run(x + 0.05)[0])
    flipped = x.copy()
    flipped[1] *= -1
    assert "qc_phase" in rules(run(flipped)[0])


# ---- clicks, gaps, jumps ------------------------------------------------------------------


def test_click_at_a_hard_cut_names_the_splice(backend):
    x = music(6)
    cut = hard_cut(2.0)
    assert "qc_click" not in rules(run(x, cut=cut)[0], "warn")
    x[:, int(2.0 * SR): int(2.0 * SR) + 2] += 0.9
    hits = [i for i in run(x, cut=cut)[0] if i.rule == "qc_click" and i.severity == "warn"]
    assert [i.splice for i in hits] == ["s1"]


def test_a_contiguous_cut_is_not_a_click_site(backend):
    """The song just plays on across this 'splice': no step can be there."""
    x = music(6)
    x[:, int(2.0 * SR): int(2.0 * SR) + 2] += 0.9
    assert "qc_click" not in rules(run(x, cut=hard_cut(2.0, same_source_contiguous=True))[0], "warn")


def test_gap_flagged_unless_at_the_edges_or_a_fade_out(backend):
    x = music(8)
    assert "qc_gap" not in rules(run(x)[0])
    x[:, 3 * SR: int(3.4 * SR)] = 0
    issues, _ = run(x)
    gap = [i for i in issues if i.rule == "qc_gap"]
    assert gap and "3." in gap[0].message
    assert "qc_gap" not in rules(run(x, fade_outs=[(2.0, 3.0)])[0])
    y = music(8)
    y[:, int(7.4 * SR):] = 0  # silence running into the end of the file
    assert "qc_gap" not in rules(run(y)[0])


def test_gain_jump_across_a_splice(backend):
    flat = music(6)
    assert "qc_gain_jump" not in rules(run(flat, cut=hard_cut(3.0))[0])
    jump = flat.copy()
    jump[:, 3 * SR:] *= 10 ** (8 / 20)
    out = [i for i in run(jump, cut=hard_cut(3.0))[0] if i.rule == "qc_gain_jump"]
    assert len(out) == 1 and out[0].splice == "s1" and out[0].node == "n2"


def test_tilt_jump_across_a_splice(backend):
    dark = signal.sosfilt(signal.butter(4, 1000, "lowpass", fs=SR, output="sos"),
                          RNG.standard_normal((2, 3 * SR)), axis=-1)
    bright = signal.sosfilt(signal.butter(4, 3000, "highpass", fs=SR, output="sos"),
                            RNG.standard_normal((2, 3 * SR)), axis=-1)
    dark, bright = (0.1 * dark / dark.std()).astype(np.float32), (0.1 * bright / bright.std()).astype(np.float32)
    assert "qc_tilt_jump" not in rules(run(np.hstack([dark, dark]), cut=hard_cut(3.0))[0])
    assert "qc_tilt_jump" in rules(run(np.hstack([dark, bright]), cut=hard_cut(3.0))[0])


# ---- sources, backends, engine ------------------------------------------------------------


def test_bandwidth_flags_a_low_passed_source():
    noise = RNG.standard_normal((2, 12 * SR)).astype(np.float32) * 0.1
    low = signal.sosfilt(signal.butter(10, 10000, "lowpass", fs=SR, output="sos"), noise, axis=-1)
    x = music(2)
    issues, inf = run(x, sources={"full": Audio(noise, SR), "low": Audio(low.astype(np.float32), SR)})
    bw = [i for i in issues if i.rule == "qc_bandwidth"]
    assert len(bw) == 1 and "'low'" in bw[0].message and bw[0].severity == "info"
    assert 10000 < inf.qc["bandwidth_hz"]["low"] < 14500  # 40 dB down on a gentle slope and inf.qc["bandwidth_hz"]["full"] > 19000


def test_backend_note_when_essentia_is_missing(monkeypatch):
    monkeypatch.setenv("RECUT_QC_ESSENTIA", "1")
    monkeypatch.setattr(qc_essentia, "_ES", False)
    issues, inf = run(music(3))
    note = [i for i in issues if i.rule == "qc_backend"]
    assert len(note) == 1 and note[0].severity == "info" and inf.qc["backend"] == "basic"


def test_switch_off_uses_basic_without_a_note(monkeypatch):
    monkeypatch.setenv("RECUT_QC_ESSENTIA", "0")
    issues, inf = run(music(3))
    assert inf.qc["backend"] == "basic" and "qc_backend" not in rules(issues)


def test_essentia_backend_is_used_when_installed(monkeypatch):
    pytest.importorskip("essentia")
    monkeypatch.setenv("RECUT_QC_ESSENTIA", "1")
    assert run(music(3))[1].qc["backend"] == "essentia"


@pytest.mark.parametrize("env", ["0", "1"])
def test_demo_renders_have_no_qc_errors_and_write_numbers(demo, monkeypatch, env):
    if env == "1":
        pytest.importorskip("essentia")
    monkeypatch.setenv("RECUT_QC_ESSENTIA", env)
    root, tid = demo
    for k in (1, 2):
        tickets.render_iteration(tid, 1, k, root)  # re-render under this backend
        r = json.loads((tickets.iteration_dir(tid, 1, k, root) / "render.json").read_text())
        assert [i for i in r["issues"] if i["rule"].startswith("qc_") and i["severity"] == "error"] == []
        assert {"lufs", "true_peak_dbtp", "timings_ms"} <= set(r["qc"])
        assert "peak_clip" not in {i["rule"] for i in r["issues"]}
