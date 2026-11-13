"""Insert devices for clips, tracks, returns and master (PLAN §3.2 device table).

Every device is a function (device, audio[2, N], Ctx) -> audio[2, N] of the same length;
the engine pads the buffer when a tail is wanted (see tail_seconds).

Automation (`devices.<id>.<param>`, AUTOMATABLE below): a per-sample curve comes from
recut.automation. Level-like parameters (utility gain/width, dry_wet) are applied per
sample; filter parameters that pedalboard can't change per sample are updated once per
BLOCK (512) samples on a stateful board (`reset=False`), the same approach reverb_sweep
uses for its dry/wet mix.

Auto Filter: pedalboard LadderFilter, 12 dB/oct; `resonance` 0-1.25 is scaled to its 0-1.
EQ: low_cut/high_cut are two cascaded first-order pedalboard Highpass/LowpassFilters
(12 dB/oct), bands are peak filters.
Delay: own comb/ping-pong loop with the filters inside the feedback path (each repeat is
band-limited again); `time` is resolved at the owner's tempo.

Reverb: pedalboard's Freeverb has no decay-time parameter, so `decay` (seconds) is mapped
to Freeverb's room_size by interpolating RT60 measured with an impulse (damping 0.5,
T30 x 2); see REVERB_DECAY_TABLE. Decays below 0.53 s or above 9.5 s are clamped.
`size` (0-100) scales the decay (x0.7 at 0, x1.0 at 50, x1.3 at 100). The wet signal is
level-compensated (REVERB_WET_GAIN_DB) so a 100% wet reverb is about as loud as its input.
"""

import math
from dataclasses import dataclass, field

import numpy as np
from pedalboard import (  # type: ignore
    HighpassFilter,
    LadderFilter,
    LowpassFilter,
    PeakFilter,
    Pedalboard,
)
from pedalboard import Limiter as PbLimiter
from pedalboard import Reverb as PbReverb

from recut.automation import build_curve
from recut.contracts.plan import Automation, Device
from recut.contracts.units import db_to_gain, parse_time

# (room_size, measured decay in seconds)
REVERB_DECAY_TABLE = [
    (0.0, 0.53), (0.1, 0.59), (0.2, 0.67), (0.3, 0.77), (0.4, 0.90), (0.5, 1.08),
    (0.6, 1.33), (0.7, 1.73), (0.8, 2.40), (0.9, 3.88), (0.95, 5.52), (1.0, 9.54),
]


# (room_size, level of a 100% wet Freeverb vs its input for steady noise, dB). The reverb
# device subtracts it, so dry_wet=100 on a return is about as loud as the signal sent in.
REVERB_WET_GAIN_DB = [
    (0.0, 1.6), (0.1, 1.8), (0.2, 2.0), (0.3, 2.3), (0.4, 2.6), (0.5, 2.9),
    (0.6, 3.3), (0.7, 3.8), (0.8, 4.4), (0.9, 5.3), (0.95, 6.0), (1.0, 7.1),
]


def decay_to_room_size(decay_s: float) -> float:
    rooms, decays = zip(*REVERB_DECAY_TABLE)
    return float(np.interp(decay_s, decays, rooms))


@dataclass
class Ctx:
    sr: int
    bpm: float
    bpb: int
    length_s: float  # owner length, for `at: "end"` automation
    autos: list[Automation] = field(default_factory=list)
    limited: bool = False  # set when a limiter device actually reduced the signal
    trim_db: float = 0.0  # static true-peak trim the limiter applied (dB, <= 0); QC discounts it

    def curve(self, dev, param: str, n: int):
        """Per-sample automation curve for devices.<id>.<param>, or None. Level kinds are linear gain."""
        kind = AUTOMATABLE.get(dev.type, {}).get(param, "linear")
        return build_curve(self.autos, f"devices.{dev.id}.{param}", n, self.sr, self.bpm, self.bpb,
                           kind, self.length_s)


# automatable parameters per device and how their curve is interpolated
AUTOMATABLE: dict[str, dict[str, str]] = {
    "utility": {"gain": "level", "width": "linear"},
    "eq": {"low_cut": "freq", "high_cut": "freq"},
    "auto_filter": {"frequency": "freq", "resonance": "linear"},
    "reverb": {"dry_wet": "linear", "hi_cut": "freq"},
    "delay": {"dry_wet": "linear", "feedback": "linear", "filter_lo": "freq", "filter_hi": "freq"},
    "limiter": {},
}

BLOCK = 512


TRUE_PEAK_TOP = 50_000  # candidate peaks oversampled when trimming (a limited master has many)


def limit(x: np.ndarray, sr: int, ceiling_db: float) -> tuple[np.ndarray, float]:
    """Limit to `ceiling_db`, true-peak aware. Returns (audio, static trim in dB, <= 0).

    1. pedalboard's (JUCE) Limiter holds the *sample* peak at the threshold and normalizes to
       0 dBFS, so rescale to the ceiling.
    2. Sample peaks at the ceiling can reconstruct (4x oversampled, BS.1770) above it by
       0.2 to 1 dB on a loud master, which made `qc_true_peak` fire on every limited render. So
       measure the 4x true peak and, when it is over the ceiling, apply one static gain trim
       that brings it down to the ceiling. A static trim is inaudible (about 1 dB for the whole
       render) and simpler and safer than an oversampled look-ahead limiter; the cost is that
       the sample peaks sit that much below the ceiling. QC discounts the trim when it measures
       limiter gain reduction (it is a level offset, not squash).
    """
    y = Pedalboard([PbLimiter(threshold_db=ceiling_db)])(x, sr) * (10 ** (ceiling_db / 20))
    return trim_true_peak(y.astype(np.float32), ceiling_db)


def trim_true_peak(y: np.ndarray, ceiling_db: float) -> tuple[np.ndarray, float]:
    """Scale `y` down so its 4x-oversampled peak is at `ceiling_db` (minus a 0.01 dB margin for
    the oversampling estimate); untouched if already under. Returns (audio, trim in dB)."""
    from recut.qc import true_peak

    _, tp = true_peak(y, top=TRUE_PEAK_TOP)
    ceil = 10 ** ((ceiling_db - 0.01) / 20)
    if tp <= ceil:
        return y, 0.0
    return (y * (ceil / tp)).astype(np.float32), 20 * math.log10(ceil / tp)


def _clampf(f: float, sr: int, lo: float = 10.0) -> float:
    return float(min(max(f, lo), sr * 0.45))


def _run(board: Pedalboard, x: np.ndarray, sr: int, setters: list) -> np.ndarray:
    """Run `board` over x. setters = [(plugin, attr, curve | None, transform)]: curves are
    sampled once per BLOCK samples; with none, the board runs in a single call."""
    live = [s for s in setters if s[2] is not None]
    if not live:
        return board(x, sr)
    out = np.empty_like(x)
    for i in range(0, x.shape[-1], BLOCK):
        for plugin, attr, curve, tf in live:
            setattr(plugin, attr, tf(float(curve[i])))
        out[:, i:i + BLOCK] = board(x[:, i:i + BLOCK], sr, reset=(i == 0))
    return out


def _mix(x: np.ndarray, wet: np.ndarray, dry_wet, ctx: Ctx, dev) -> np.ndarray:
    c = ctx.curve(dev, "dry_wet", x.shape[-1])
    w = dry_wet / 100 if c is None else c / 100
    return (x * (1 - w) + wet * w).astype(np.float32)


def _utility(dev, x, ctx):
    n = x.shape[-1]
    g, wd = ctx.curve(dev, "gain", n), ctx.curve(dev, "width", n)
    if wd is not None or dev.width != 100:
        w = (dev.width if wd is None else wd) / 100
        mid, side = (x[0] + x[1]) / 2, (x[0] - x[1]) / 2 * w
        x = np.stack([mid + side, mid - side])
    return (x * (db_to_gain(dev.gain) if g is None else g)).astype(np.float32)


def _eq(dev, x, ctx):
    n = x.shape[-1]
    plugins: list = []
    setters: list = []
    if dev.low_cut:
        curve = ctx.curve(dev, "low_cut", n)
        for _ in range(2):  # two first-order stages = 12 dB/oct
            p = HighpassFilter(cutoff_frequency_hz=_clampf(dev.low_cut, ctx.sr))
            plugins.append(p)
            setters.append((p, "cutoff_frequency_hz", curve, lambda f: _clampf(f, ctx.sr)))
    for b in dev.bands:
        plugins.append(PeakFilter(cutoff_frequency_hz=_clampf(b.frequency, ctx.sr), gain_db=b.gain, q=b.q))
    if dev.high_cut:
        curve = ctx.curve(dev, "high_cut", n)
        for _ in range(2):
            p = LowpassFilter(cutoff_frequency_hz=_clampf(dev.high_cut, ctx.sr))
            plugins.append(p)
            setters.append((p, "cutoff_frequency_hz", curve, lambda f: _clampf(f, ctx.sr)))
    if not plugins:
        return x
    return _run(Pedalboard(plugins), x, ctx.sr, setters)


_FILTER_MODES = {"lowpass": LadderFilter.Mode.LPF12, "highpass": LadderFilter.Mode.HPF12,
                 "bandpass": LadderFilter.Mode.BPF12}


def _auto_filter(dev, x, ctx):
    n = x.shape[-1]
    p = LadderFilter(mode=_FILTER_MODES[dev.filter], cutoff_hz=_clampf(dev.frequency, ctx.sr),
                     resonance=min(dev.resonance / 1.25, 1.0), drive=1.0)
    setters = [(p, "cutoff_hz", ctx.curve(dev, "frequency", n), lambda f: _clampf(f, ctx.sr)),
               (p, "resonance", ctx.curve(dev, "resonance", n), lambda r: min(max(r, 0.0), 1.25) / 1.25)]
    return _run(Pedalboard([p]), x, ctx.sr, setters)


def _reverb(dev, x, ctx):
    n = x.shape[-1]
    decay = parse_time(dev.decay, ctx.bpm, ctx.bpb) * (0.7 + 0.6 * dev.size / 100)
    room = decay_to_room_size(decay)
    wet = Pedalboard([PbReverb(room_size=room, damping=0.5, wet_level=1.0,
                               dry_level=0.0, width=dev.width / 100)])(x, ctx.sr)
    rooms, gains = zip(*REVERB_WET_GAIN_DB)
    wet = wet * (10 ** (-float(np.interp(room, rooms, gains)) / 20))
    pre = int(parse_time(dev.pre_delay, ctx.bpm, ctx.bpb) * ctx.sr)
    if pre > 0:
        wet = np.concatenate([np.zeros((wet.shape[0], pre), wet.dtype), wet[:, :-pre]], axis=-1)
    lp = LowpassFilter(cutoff_frequency_hz=_clampf(dev.hi_cut, ctx.sr))
    wet = _run(Pedalboard([lp]), wet.astype(np.float32), ctx.sr,
               [(lp, "cutoff_frequency_hz", ctx.curve(dev, "hi_cut", n), lambda f: _clampf(f, ctx.sr))])
    return _mix(x, wet, dev.dry_wet, ctx, dev)


def _delay(dev, x, ctx):
    n = x.shape[-1]
    d = max(int(parse_time(dev.time, ctx.bpm, ctx.bpb) * ctx.sr), 1)
    fb_c = ctx.curve(dev, "feedback", n)
    hp = HighpassFilter(cutoff_frequency_hz=_clampf(dev.filter_lo, ctx.sr))
    lp = LowpassFilter(cutoff_frequency_hz=_clampf(dev.filter_hi, ctx.sr))
    board = Pedalboard([hp, lp])
    lo_c, hi_c = ctx.curve(dev, "filter_lo", n), ctx.curve(dev, "filter_hi", n)
    src = x
    if dev.ping_pong:  # the input goes in on the left; repeats alternate right, left, ...
        src = np.stack([(x[0] + x[1]) / 2, np.zeros(n, dtype=x.dtype)])
    wet = np.zeros_like(x)
    prev = np.zeros((2, d), dtype=x.dtype)
    for k, a in enumerate(range(0, n, d)):
        b = min(a + d, n)
        fb = (dev.feedback if fb_c is None else fb_c[a]) / 100
        # y[n] = x[n-D] + fb * y[n-D]  (cross-channel feedback when ping-pong)
        fed = prev[::-1] if dev.ping_pong else prev
        block = (src[:, a - d:a] if k > 0 else np.zeros((2, d), dtype=x.dtype)) + fb * fed
        if lo_c is not None:
            hp.cutoff_frequency_hz = _clampf(float(lo_c[a]), ctx.sr)
        if hi_c is not None:
            lp.cutoff_frequency_hz = _clampf(float(hi_c[a]), ctx.sr)
        block = board(block.astype(np.float32), ctx.sr, reset=(k == 0))
        if k > 0:
            wet[:, a:b] = block[:, : b - a]
        prev = block
    return _mix(x, wet, dev.dry_wet, ctx, dev)


def _limiter(dev, x, ctx):
    peak = float(np.abs(x).max()) if x.size else 0.0
    if peak <= 0:
        return x
    if 20 * math.log10(peak) > dev.ceiling:
        y, trim = limit(x, ctx.sr, dev.ceiling)
    else:  # sample peaks are under the ceiling: only a true-peak overshoot needs the trim
        y, trim = trim_true_peak(x, dev.ceiling)
        if not trim:
            return x
    ctx.limited = True
    ctx.trim_db += trim
    return y


_DEVICES = {"utility": _utility, "eq": _eq, "auto_filter": _auto_filter, "reverb": _reverb,
            "delay": _delay, "limiter": _limiter}


def apply_devices(devices: list[Device], x: np.ndarray, ctx: Ctx) -> np.ndarray:
    for dev in devices:
        x = _DEVICES[dev.type](dev, np.ascontiguousarray(x, dtype=np.float32), ctx)
    return x


def tail_seconds(devices: list[Device], bpm: float, bpb: int, cap: float = 10.0) -> float:
    """How long the signal may keep ringing after the input ends (reverb/delay devices)."""
    total = 0.0
    for dev in devices:
        if dev.type == "reverb":
            total += parse_time(dev.decay, bpm, bpb) * (0.7 + 0.6 * dev.size / 100) + parse_time(dev.pre_delay, bpm, bpb)
        elif dev.type == "delay":
            t, fb = parse_time(dev.time, bpm, bpb), dev.feedback / 100
            total += t * (1 if fb <= 0 else math.ceil(math.log(1e-3) / math.log(fb)) + 1)
    return min(total, cap)
