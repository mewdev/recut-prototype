"""Q1: audio QC after render. "Is the rendered file technically clean?"

`run_qc(audio, info, ...)` returns contract `Issue`s (rules prefixed `qc_`) and, when `info`
has a `qc` field (see `RenderInfoQC`), fills it with the measured numbers. The engine calls it
at the end of `render_plan`; `render.json` carries the numbers as extra info.

Backends: Essentia (isolated in `recut.qc_essentia`, switch `RECUT_QC_ESSENTIA`) detects clicks,
discontinuities, saturation and gaps. Without it, the numpy/scipy versions below run and one
`qc_backend` info issue says so. Loudness (pyloudnorm's K-weighting, evaluated per 100 ms block
in the frequency domain: ~6x faster than `Meter.integrated_loudness`, within 0.01 LU), true
peak, limiting, and the splice-relative checks are the same either way.
"""

import math
import time
from functools import lru_cache
from typing import Optional

import numpy as np
from scipy import fft, signal

from recut import qc_essentia
from recut.audio import Audio
from recut.contracts.render import Issue, RenderInfo
from recut.qc_essentia import dedupe_times as _dedupe_times

# ---- thresholds (tuned later from review tags; see docs/workstreams/Q-quality.md) ----------
LUFS_RANGE = (-16.0, -9.0)  # absolute fallback, only when no source is available to compare with
LOUDER_THAN_SOURCE_LU = 1.0  # warn: the cut is louder than the loudest source it uses by more than this
QUIETER_THAN_SOURCE_LU = 3.0  # warn: the cut is quieter than its sources (duration-weighted) by more
LIMITING_DB = 3.0           # max gain reduction (50 ms windows)
TRUE_PEAK_DBTP = -1.0
CLIP_LEVEL = 0.999
CLIP_RUN = 3                # consecutive samples
CLICK_RATIO = 4.0           # HF energy at a splice vs the median of its neighbours (~ +6 dB)
CLICK_NEAR_S = 0.050        # Essentia hits this close to a splice name it
GAIN_JUMP_LU = 3.0
TILT_RATIO = 1.6
GAP_DB = -60.0
GAP_MIN_S = 0.200
DC_MAX = 0.01
BANDWIDTH_INFO_HZ = 15_000.0
MAX_UNATTACHED_HITS = 6     # Essentia hits away from any splice: list this many times


class RenderInfoQC(RenderInfo):
    """RenderInfo plus the extra QC numbers. The frozen contract has no `qc` field, so the
    engine returns this subclass: its `to_json()` (render.json) carries `qc`, and readers that
    validate against `RenderInfo` ignore it."""

    qc: dict = {}


def _db(x: float) -> float:
    return 20 * math.log10(x) if x > 0 else -math.inf


class _Timer:
    def __init__(self) -> None:
        self.ms: dict[str, float] = {}

    def __call__(self, name: str):
        timer = self

        class _Ctx:
            def __enter__(self):
                self.t = time.perf_counter()

            def __exit__(self, *a):
                timer.ms[name] = timer.ms.get(name, 0.0) + (time.perf_counter() - self.t) * 1000

        return _Ctx()


# ---- loudness (BS.1770 via pyloudnorm's K-weighting) --------------------------------------


@lru_cache(maxsize=8)
def _kweight_sos(sr: int) -> np.ndarray:
    import pyloudnorm as pyln

    meter = pyln.Meter(sr)
    return np.vstack([signal.tf2sos(f.b, f.a) for f in meter._filters.values()])


@lru_cache(maxsize=8)
def _kweight_power(sr: int, n: int) -> np.ndarray:
    """|H(f)|^2 of the K-weighting on an n-point rfft grid, with the one-sided doubling."""
    _, h = signal.sosfreqz(_kweight_sos(sr), worN=np.fft.rfftfreq(n, 1 / sr), fs=sr)
    w = (np.abs(h) ** 2).astype(np.float32)
    w[1:-1 if n % 2 == 0 else None] *= 2
    return w


def _block_energy(x: np.ndarray, sr: int) -> np.ndarray:
    """K-weighted mean square per 100 ms block, (channels, blocks)."""
    n = sr // 10
    nb = x.shape[-1] // n
    if nb < 4:
        return np.zeros((x.shape[0], 0))
    spec = fft.rfft(x[:, : nb * n].reshape(x.shape[0], nb, n), axis=-1, workers=-1)
    return ((spec.real**2 + spec.imag**2) * _kweight_power(sr, n)).sum(-1) / (n * n)


def integrated_lufs(x: np.ndarray, sr: int) -> Optional[float]:
    z100 = _block_energy(x, sr)
    if z100.shape[1] < 4:
        return None
    nb = z100.shape[1]
    z = sum(z100[:, i: nb - 3 + i] for i in range(4)) / 4  # 400 ms blocks, 100 ms hop
    lk = -0.691 + 10 * np.log10(z.sum(0) + 1e-20)
    gated = lk > -70
    if not gated.any():
        return None
    thr = -0.691 + 10 * np.log10(z[:, gated].mean(1).sum()) - 10
    gated &= lk > thr
    return float(-0.691 + 10 * np.log10(z[:, gated].mean(1).sum())) if gated.any() else None


def source_loudness(info: RenderInfo, sources: dict[str, Audio]) -> Optional[dict]:
    """Integrated loudness of the parts of each source the cut actually uses (the segments'
    source ranges, concatenated per source), and each source's share of the used duration.
    Returns {"per_source": {id: lufs}, "weights": {id: seconds}, "loudest": lufs, "weighted": lufs}
    or None when no used source is long enough to measure."""
    used: dict[str, list[tuple[float, float]]] = {}
    for s in info.segments:
        if s.source in sources and s.src_end > s.src_start:
            used.setdefault(s.source, []).append((s.src_start, s.src_end))
    per: dict[str, float] = {}
    weights: dict[str, float] = {}
    for sid, spans in used.items():
        a = sources[sid]
        x = a.samples if a.samples.ndim == 2 else np.stack([a.samples, a.samples])
        parts = [x[:, int(lo * a.sr): int(hi * a.sr)] for lo, hi in spans]
        parts = [q for q in parts if q.shape[-1]]
        if not parts:
            continue
        lufs = integrated_lufs(np.concatenate(parts, axis=-1).astype(np.float32), a.sr)
        if lufs is not None:
            per[sid] = lufs
            weights[sid] = sum(hi - lo for lo, hi in spans)
    if not per:
        return None
    tot = sum(weights.values())
    return {"per_source": per, "weights": weights, "loudest": max(per.values()),
            "weighted": sum(per[k] * weights[k] for k in per) / tot}


def _momentary(x: np.ndarray, sr: int, a: int, b: int) -> Optional[float]:
    """Loudness of x[:, a:b] (K-weighted, filter warmed up on 250 ms before it); None if silent."""
    lo = max(0, a - int(0.25 * sr))
    seg = signal.sosfilt(_kweight_sos(sr), x[:, lo:b].astype(np.float64), axis=-1)[:, a - lo:]
    if seg.shape[-1] < 0.2 * sr:
        return None
    z = float((seg**2).mean(-1).sum())
    lufs = -0.691 + 10 * math.log10(z + 1e-20)
    return lufs if lufs > -60 else None


# ---- peaks ------------------------------------------------------------------------------


def peak_env(x: np.ndarray) -> np.ndarray:
    """Per-sample max |x| over the channels (shared by the peak, limiting and clipping checks)."""
    return np.maximum(np.abs(x[0]), np.abs(x[1])) if x.shape[0] > 1 else np.abs(x[0])


def true_peak(x: np.ndarray, a: Optional[np.ndarray] = None, top: int = 800) -> tuple[float, float]:
    """(sample peak, true peak), linear. Oversamples 4x only around the `top` largest local
    maxima above 70 % of the sample peak: inter-sample overshoot needs a large sample beside it
    (verified against full 4x oversampling in the tests)."""
    a = peak_env(x) if a is None else a
    sp = float(a.max()) if a.size else 0.0
    cand = np.flatnonzero(a > max(sp * 0.7, 1e-4))
    cand = cand[(cand > 0) & (cand < a.size - 1)]
    cand = cand[(a[cand] >= a[cand - 1]) & (a[cand] >= a[cand + 1])]
    if cand.size == 0:
        return sp, sp
    if cand.size > top:
        cand = cand[np.argpartition(a[cand], -top)[-top:]]
    half = 16
    pad = np.pad(x, ((0, 0), (half, half)))
    win = np.stack([pad[:, c: c + 2 * half + 1] for c in cand])        # (k, ch, 33)
    up = signal.resample_poly(win, 4, 1, axis=-1)                      # (k, ch, 132)
    mid = np.abs(up[..., 4 * 8: 4 * 25])                               # away from the edges
    return sp, max(sp, float(mid.max()))


def max_gain_reduction(pre: np.ndarray, a_out: np.ndarray, sr: int) -> float:
    """Largest drop of the windowed (50 ms) peak from the pre-master mix to the output, dB."""
    n = max(1, int(0.05 * sr))
    a_pre = peak_env(pre)
    total = min(a_pre.size, a_out.size) // n * n
    if total == 0:
        return 0.0
    p = a_pre[:total].reshape(-1, n).max(1)
    o = a_out[:total].reshape(-1, n).max(1)
    live = p > 1e-3
    if not live.any():
        return 0.0
    return float(max(0.0, (20 * np.log10(p[live] / np.maximum(o[live], 1e-9))).max()))


def clip_runs(a: np.ndarray, sr: int) -> list[tuple[float, int]]:
    """Runs of >= CLIP_RUN consecutive samples at |x| >= CLIP_LEVEL (either channel):
    [(time_s, length)]."""
    idx = np.flatnonzero(a >= CLIP_LEVEL)
    if idx.size < CLIP_RUN:
        return []
    cuts = np.flatnonzero(np.diff(idx) > 1) + 1
    starts, ends = np.concatenate([[0], cuts]), np.concatenate([cuts, [idx.size]])
    return [(float(idx[s]) / sr, int(e - s)) for s, e in zip(starts, ends) if e - s >= CLIP_RUN]


# ---- splice-relative checks ---------------------------------------------------------------

_HP4K: dict[int, np.ndarray] = {}


def click_ratio(mono: np.ndarray, sr: int, t: float) -> float:
    """HF (> 4 kHz) energy in the 20 ms around t vs the median of ten neighbouring 20 ms windows
    (five either side, leaving the adjacent ones out)."""
    w = int(0.020 * sr)
    lo = int(t * sr) - 6 * w - w // 2
    warm = sr // 20
    if lo < 0 or lo + 13 * w > mono.size:
        return 0.0
    if sr not in _HP4K:
        _HP4K[sr] = signal.butter(4, 4000, "highpass", fs=sr, output="sos")
    seg = mono[max(0, lo - warm): lo + 13 * w].astype(np.float64)
    y = signal.sosfilt(_HP4K[sr], seg)[min(lo, warm):]
    e = (y[: 13 * w].reshape(13, w) ** 2).mean(1)
    if e[6] < 1e-7:  # below -70 dBFS: nothing to click
        return 0.0
    return float(e[6] / max(float(np.median(e[[1, 2, 3, 4, 5, 7, 8, 9, 10, 11]])), 1e-12))


def centroid(mono: np.ndarray, sr: int) -> Optional[float]:
    if mono.size < sr // 4 or float(np.sqrt((mono.astype(np.float64) ** 2).mean())) < 1e-3:
        return None
    mag = np.abs(fft.rfft(mono * np.hanning(mono.size), workers=-1))
    f = np.fft.rfftfreq(mono.size, 1 / sr)
    s = float(mag.sum())
    return float((f * mag).sum() / s) if s > 0 else None


def bandwidth_hz(x: np.ndarray, sr: int, chunks: int = 24, n: int = 4096) -> Optional[float]:
    """Highest frequency whose long-term level is within 40 dB of the median level of 100 Hz to 8 kHz,
    from `chunks` evenly spaced frames of the mono mix (silent frames skipped)."""
    if x.shape[-1] < n * 4:
        return None
    starts = np.linspace(0, x.shape[-1] - n, chunks).astype(int)
    frames = np.stack([x[:, s: s + n].mean(0) for s in starts])
    frames = frames[np.sqrt((frames**2).mean(1)) > 1e-3]
    if len(frames) < 4:
        return None
    psd = (np.abs(fft.rfft(frames * np.hanning(n), axis=-1, workers=-1)) ** 2).mean(0)
    f = np.fft.rfftfreq(n, 1 / sr)
    k = 21  # ~100 Hz smoothing so single bins don't set the edge
    db = 10 * np.log10(np.convolve(psd, np.ones(k) / k, mode="same") + 1e-20)
    ref = np.median(db[(f >= 100) & (f <= 8000)])  # level of the music body, not of the empty top
    above = np.flatnonzero((f >= 100) & (db >= ref - 40))
    return float(f[above[-1]]) if above.size else None


# ---- the entry point ----------------------------------------------------------------------


def _step_times(info: RenderInfo, sp) -> list[float]:
    """Output times where this join can leave a step in the waveform: a hard cut, or an xfade
    side that is `hold` (full level up to / from the overlap edge). Smooth ramps and cuts that
    are contiguous in one source (the song simply plays on) have none."""
    seg = {s.node_id: s for s in info.segments}
    a, b = seg.get(sp.from_), seg.get(sp.to)
    t, t_end = sp.out_time, sp.out_time + sp.overlap_ms / 1000
    if sp.overlap_ms <= 0:
        if a and b and a.source == b.source and abs(a.src_end - b.src_start) < 0.001:
            return []
        return [t]
    return ([t] if sp.in_shape == "hold" else []) + ([t_end] if sp.out_shape == "hold" else [])


def _nearest_splice(info: RenderInfo, t: float, within: float = CLICK_NEAR_S, steps: bool = False):
    best = None
    for sp in info.splices:
        pts = _step_times(info, sp) if steps else [sp.out_time, sp.out_time + sp.overlap_ms / 1000]
        for tt in pts:
            d = abs(tt - t)
            if d <= within and (best is None or d < best[0]):
                best = (d, sp.id)
    return best[1] if best else None


def run_qc(audio: Audio, info: RenderInfo, *, pre_master: Optional[np.ndarray] = None,
           sources: Optional[dict[str, Audio]] = None,
           fade_outs: Optional[list[tuple[float, float]]] = None,
           trim_db: float = 0.0) -> list[Issue]:
    """All `qc_*` checks on the rendered audio.

    `pre_master`: the mix before the master chain (for `qc_limiting`; skipped without it).
    `sources`: source id -> Audio (for `qc_bandwidth`). `fade_outs`: output-time spans of
    deliberate clip fade-outs, which `qc_gap` ignores. `trim_db`: the master limiter's static
    true-peak trim (<= 0), discounted from `qc_limiting` (a level offset, not squash). Fills `info.qc` when it has that field.
    """
    x = audio.samples
    if x.ndim == 1:
        x = np.stack([x, x])
    x = np.asarray(x, dtype=np.float32)
    sr = audio.sr
    total = x.shape[-1] / sr
    issues: list[Issue] = []
    qc: dict = {}
    tm = _Timer()
    if x.shape[-1] == 0:
        return issues
    with tm("mono"):
        mono = (x[0] + x[-1]) * 0.5 if x.shape[0] > 1 else x[0]
        env = peak_env(x)

    # -- backend note
    use_es = qc_essentia.available()
    qc["backend"] = "essentia" if use_es else "basic"
    if qc_essentia.enabled() and not use_es:
        issues.append(Issue(severity="info", rule="qc_backend",
                            message="essentia not installed, using basic detectors"))

    # -- loudness: relative to the sources the cut uses. A loud master is not a defect in itself;
    # what matters is that the edit didn't make it louder (gain, reverb build-up) or drop its level.
    with tm("loudness"):
        lufs = integrated_lufs(x, sr)
        ref = source_loudness(info, sources) if sources else None
    qc["lufs"] = None if lufs is None else round(lufs, 2)
    if ref is not None:
        qc["source_lufs"] = {k: round(v, 2) for k, v in ref["per_source"].items()}
    if lufs is not None and ref is not None:
        qc["lufs_vs_source"] = round(lufs - ref["weighted"], 2)
        if lufs - ref["loudest"] > LOUDER_THAN_SOURCE_LU:
            issues.append(Issue(severity="warn", rule="qc_loudness",
                                message=f"the cut is {lufs - ref['loudest']:.1f} LU louder than its loudest "
                                        f"source ({lufs:.1f} vs {ref['loudest']:.1f} LUFS): lower a gain "
                                        f"or a send"))
        elif ref["weighted"] - lufs > QUIETER_THAN_SOURCE_LU:
            issues.append(Issue(severity="warn", rule="qc_loudness",
                                message=f"the cut is {ref['weighted'] - lufs:.1f} LU quieter than its "
                                        f"sources ({lufs:.1f} vs {ref['weighted']:.1f} LUFS): unintended "
                                        f"level drop?"))
    elif lufs is not None and not LUFS_RANGE[0] <= lufs <= LUFS_RANGE[1]:
        issues.append(Issue(severity="warn", rule="qc_loudness",
                            message=f"integrated loudness {lufs:.1f} LUFS (expected "
                                    f"{LUFS_RANGE[0]:.0f} to {LUFS_RANGE[1]:.0f}; no source to compare with)"))

    # -- limiting (pre-master vs output, 50 ms windows)
    if pre_master is not None and info.limiter_applied:
        with tm("limiting"):
            gr = max_gain_reduction(pre_master, env * 10 ** (-trim_db / 20), sr)
        qc["max_gain_reduction_db"] = round(gr, 2)
        qc["true_peak_trim_db"] = round(trim_db, 2)
        if gr > LIMITING_DB:
            issues.append(Issue(severity="warn", rule="qc_limiting",
                                message=f"the master limiter pulls the level down by up to {gr:.1f} dB "
                                        f"(above {LIMITING_DB:.0f} dB is audible squash): lower clip "
                                        f"gain or sends"))
    elif pre_master is not None:
        qc["max_gain_reduction_db"] = 0.0

    # -- true peak
    with tm("true_peak"):
        sp, tp = true_peak(x, env)
    qc["sample_peak_dbfs"] = round(_db(sp), 2)
    qc["true_peak_dbtp"] = round(_db(tp), 2)
    if _db(tp) > TRUE_PEAK_DBTP:
        issues.append(Issue(severity="warn", rule="qc_true_peak",
                            message=f"true peak {_db(tp):+.1f} dBTP (above {TRUE_PEAK_DBTP:+.1f})"))

    # -- DC / phase
    with tm("dc_phase"):
        dc = float(np.abs(x.mean(-1)).max())
        lc, rc = x[0], x[1]
        den = math.sqrt(float(np.dot(lc, lc)) * float(np.dot(rc, rc)))
        corr = float(np.dot(lc, rc)) / den if den > 0 else 1.0
    qc["dc_offset"] = round(dc, 5)
    qc["lr_correlation"] = None if not math.isfinite(corr) else round(corr, 3)
    if dc > DC_MAX:
        issues.append(Issue(severity="warn", rule="qc_dc", message=f"DC offset {dc:.3f}"))
    if math.isfinite(corr) and corr < 0:
        issues.append(Issue(severity="warn", rule="qc_phase",
                            message=f"left/right correlation {corr:.2f}: mono sum will cancel"))

    # -- Essentia, once on the mono render
    det = None
    if use_es:
        with tm("essentia"):
            det = qc_essentia.detect(mono, sr)

    # -- clipping
    with tm("clipping"):
        if det is not None:
            clip_hits = [(a, max(1, int(round((b - a) * sr)))) for a, b in det.saturation]
        else:
            clip_hits = clip_runs(env, sr)
    qc["clip_hits"] = len(clip_hits)
    for t, n in clip_hits[:3]:
        issues.append(Issue(severity="error", rule="qc_clipping", splice=_nearest_splice(info, t),
                            message=f"clipped samples at {t:.2f}s ({n} in a row)"))
    if len(clip_hits) > 3:
        issues.append(Issue(severity="error", rule="qc_clipping",
                            message=f"{len(clip_hits) - 3} more clipped runs"))

    # -- clicks
    with tm("click"):
        if det is not None:
            hits = _dedupe_times(det.clicks + det.discontinuities)
            away = []
            for t in hits:
                sid = _nearest_splice(info, t, steps=True)
                if sid is None:
                    away.append(t)
                else:
                    issues.append(Issue(severity="warn", rule="qc_click", splice=sid,
                                        message=f"{sid}: click or discontinuity at {t:.2f}s"))
            if away:  # source transients, not edit artifacts: don't call them defects
                shown = ", ".join(f"{t:.1f}s" for t in away[:MAX_UNATTACHED_HITS])
                issues.append(Issue(severity="info", rule="qc_click",
                                    message=f"{len(away)} click-like transients away from any splice "
                                            f"(first: {shown})"))
            qc["click_hits"] = len(hits)
        else:
            n_hits = 0
            for sp_ in info.splices:
                r = max((click_ratio(mono, sr, t) for t in _step_times(info, sp_)), default=0.0)
                if r > CLICK_RATIO:
                    n_hits += 1
                    issues.append(Issue(severity="warn", rule="qc_click", splice=sp_.id,
                                        message=f"{sp_.id}: possible click, high-frequency energy "
                                                f"{10 * math.log10(r):.0f} dB above its surroundings"))
            qc["click_hits"] = n_hits

    # -- gaps
    with tm("gap"):
        ignore = [(a - 0.1, b + 0.5) for a, b in (fade_outs or [])]
        if det is not None:
            gaps = [(a, b) for a, b in det.gaps]
        else:
            n10 = max(1, int(0.010 * sr))
            nb = mono.size // n10
            rms_db = 10 * np.log10((mono[: nb * n10].reshape(nb, n10) ** 2).mean(1) + 1e-20)
            quiet = np.concatenate([[0], (rms_db < GAP_DB).view(np.int8), [0]])
            d = np.diff(quiet)
            gaps = [(s * 0.010, e * 0.010) for s, e in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1))
                    if (e - s) * 0.010 > GAP_MIN_S]
        gaps = [(a, b) for a, b in gaps
                if a > 0.5 and b < total - 0.5 and not any(a < hi and b > lo for lo, hi in ignore)]
    qc["gap_hits"] = len(gaps)
    for a, b in gaps[:5]:
        issues.append(Issue(severity="warn", rule="qc_gap", splice=_nearest_splice(info, a, 0.25),
                            message=f"near-silence from {a:.2f}s to {b:.2f}s ({(b - a) * 1000:.0f} ms)"))

    # -- per-splice: gain jump, tilt jump
    with tm("splice_jumps"):
        for sp_ in info.splices:
            t_in = sp_.out_time
            t_after = sp_.out_time + sp_.overlap_ms / 1000
            n400 = int(0.4 * sr)
            b1, a0 = int(t_in * sr), int(t_after * sr)
            if b1 - n400 >= 0 and a0 + n400 <= x.shape[-1]:
                before, after = _momentary(x, sr, b1 - n400, b1), _momentary(x, sr, a0, a0 + n400)
                if before is not None and after is not None and abs(after - before) > GAIN_JUMP_LU:
                    issues.append(Issue(severity="warn", rule="qc_gain_jump", splice=sp_.id, node=sp_.to,
                                        message=f"{sp_.id}: loudness jumps {after - before:+.1f} LU "
                                                f"across the splice ({before:.1f} to {after:.1f} LUFS)"))
            n1s = sr
            if b1 - n1s >= 0 and a0 + n1s <= mono.size:
                c1, c2 = centroid(mono[b1 - n1s: b1], sr), centroid(mono[a0: a0 + n1s], sr)
                if c1 and c2 and max(c1, c2) / min(c1, c2) > TILT_RATIO:
                    issues.append(Issue(severity="warn", rule="qc_tilt_jump", splice=sp_.id, node=sp_.to,
                                        message=f"{sp_.id}: brightness jumps across the splice "
                                                f"(spectral centroid {c1:.0f} Hz to {c2:.0f} Hz): "
                                                f"EQ or filter mismatch"))

    # -- per-source bandwidth
    if sources:
        with tm("bandwidth"):
            qc["bandwidth_hz"] = {}
            for sid, src in sources.items():
                s = src.samples if src.samples.ndim == 2 else np.stack([src.samples, src.samples])
                bw = bandwidth_hz(s, src.sr)
                qc["bandwidth_hz"][sid] = None if bw is None else round(bw)
                if bw is not None and bw < BANDWIDTH_INFO_HZ:
                    issues.append(Issue(severity="info", rule="qc_bandwidth",
                                        message=f"source {sid!r} has nothing above {bw / 1000:.1f} kHz "
                                                f"(low-quality source)"))

    qc["timings_ms"] = {k: round(v, 1) for k, v in tm.ms.items()}
    qc["total_ms"] = round(sum(tm.ms.values()), 1)
    if hasattr(info, "qc"):
        info.qc = qc  # type: ignore[attr-defined]
    return issues
