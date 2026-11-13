"""Insert devices for clips, tracks, returns and master (PLAN §3.2 device table).

Every device is a function (device, audio[2, N], Ctx) -> audio[2, N] of the same length;
the engine pads the buffer when a tail is wanted.

Reverb: pedalboard's Freeverb has no decay-time parameter, so `decay` (seconds) is mapped
to Freeverb's room_size by interpolating RT60 measured with an impulse (damping 0.5,
T30 x 2); see REVERB_DECAY_TABLE. Decays below 0.53 s or above 9.5 s are clamped.
`size` (0-100) scales the decay (x0.7 at 0, x1.0 at 50, x1.3 at 100). The wet signal is
level-compensated (REVERB_WET_GAIN_DB) so a 100% wet reverb is about as loud as its input.
"""

import math
from dataclasses import dataclass, field

import numpy as np
from pedalboard import Limiter as PbLimiter
from pedalboard import LowpassFilter, Pedalboard  # type: ignore
from pedalboard import Reverb as PbReverb

from recut.contracts.plan import Automation, Device
from recut.contracts.units import parse_time

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


def limit(x: np.ndarray, sr: int, ceiling_db: float) -> np.ndarray:
    """Limit to `ceiling_db`. pedalboard's (JUCE) Limiter normalizes to 0 dBFS → rescale."""
    return Pedalboard([PbLimiter(threshold_db=ceiling_db)])(x, sr) * (10 ** (ceiling_db / 20))


def _reverb(dev, x: np.ndarray, ctx: Ctx) -> np.ndarray:
    decay = parse_time(dev.decay, ctx.bpm, ctx.bpb) * (0.7 + 0.6 * dev.size / 100)
    room = decay_to_room_size(decay)
    wet = Pedalboard([PbReverb(room_size=room, damping=0.5, wet_level=1.0,
                               dry_level=0.0, width=dev.width / 100)])(x, ctx.sr)
    rooms, gains = zip(*REVERB_WET_GAIN_DB)
    wet = wet * (10 ** (-float(np.interp(room, rooms, gains)) / 20))
    pre = int(parse_time(dev.pre_delay, ctx.bpm, ctx.bpb) * ctx.sr)
    if pre > 0:
        wet = np.concatenate([np.zeros((wet.shape[0], pre), wet.dtype), wet[:, :-pre]], axis=-1)
    wet = Pedalboard([LowpassFilter(cutoff_frequency_hz=min(dev.hi_cut, ctx.sr * 0.45))])(wet, ctx.sr)
    w = dev.dry_wet / 100
    return (x * (1 - w) + wet * w).astype(np.float32)


def _limiter(dev, x: np.ndarray, ctx: Ctx) -> np.ndarray:
    peak = float(np.abs(x).max()) if x.size else 0.0
    if peak > 0 and 20 * math.log10(peak) > dev.ceiling:
        ctx.limited = True
        return limit(x, ctx.sr, dev.ceiling)
    return x


_DEVICES = {"reverb": _reverb, "limiter": _limiter}


def is_supported(dev: Device) -> bool:
    return dev.type in _DEVICES


def apply_devices(devices: list[Device], x: np.ndarray, ctx: Ctx) -> np.ndarray:
    for dev in devices:
        x = _DEVICES[dev.type](dev, x, ctx)
    return x
