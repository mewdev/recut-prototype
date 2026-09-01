"""
Typed, serializable fx (OTIO-inspired) — replaces Clip.fx: list[Callable].

Each Effect subclass mirrors one curried primitive's kwargs exactly, so
to_fn() can rebuild the callable with **asdict(self) — no per-field mapping.
"""

from dataclasses import asdict, dataclass
from typing import Callable, ClassVar

from recut.audio import Audio
from recut.primitives.curves import Curve
from recut.primitives.delay import delay
from recut.primitives.fade import fade
from recut.primitives.filter_sweep import FilterType, filter_sweep
from recut.primitives.reverb import ReverbType, reverb, reverb_sweep


@dataclass
class Effect:
    _primitive: ClassVar[Callable]
    type: ClassVar[str]

    def to_fn(self) -> Callable[[Audio], Audio]:
        return self._primitive(**asdict(self))

    def to_json(self) -> dict:
        return {"type": self.type, "params": asdict(self)}


@dataclass
class Fade(Effect):
    _primitive: ClassVar[Callable] = staticmethod(fade)
    type: ClassVar[str] = "fade"

    vol_start: float = 0.0
    vol_end: float = 1.0
    curve: Curve = "linear"


@dataclass
class Reverb(Effect):
    _primitive: ClassVar[Callable] = staticmethod(reverb)
    type: ClassVar[str] = "reverb"

    wetness: float = 0.4
    reverb_type: ReverbType = "hall"
    room_size: float | None = None
    damping: float | None = None
    width: float | None = None


@dataclass
class ReverbSweep(Effect):
    _primitive: ClassVar[Callable] = staticmethod(reverb_sweep)
    type: ClassVar[str] = "reverb_sweep"

    wetness_start: float = 0.0
    wetness_end: float = 0.4
    reverb_type: ReverbType = "hall"
    room_size: float | None = None
    damping: float | None = None
    width: float | None = None
    duration: float | None = None
    curve: Curve = "qsin"


@dataclass
class Delay(Effect):
    _primitive: ClassVar[Callable] = staticmethod(delay)
    type: ClassVar[str] = "delay"

    delay_seconds: float = 0.5
    feedback: float = 0.0
    mix: float = 0.5


@dataclass
class FilterSweep(Effect):
    _primitive: ClassVar[Callable] = staticmethod(filter_sweep)
    type: ClassVar[str] = "filter_sweep"

    filter_type: FilterType = "low"
    freq_start: float = 200.0
    freq_end: float = 20000.0
    duration: float | None = None
    curve: float = 1.0


EFFECT_TYPES: dict[str, type[Effect]] = {
    "fade": Fade,
    "reverb": Reverb,
    "reverb_sweep": ReverbSweep,
    "delay": Delay,
    "filter_sweep": FilterSweep,
}


def effect_from_json(node: dict) -> Effect:
    return EFFECT_TYPES[node["type"]](**node["params"])
