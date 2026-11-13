"""Units used in plan.json (PLAN §3.2): musical/clock time strings, dB levels, shapes.

One rule per kind of value so agents cannot mix them up:
  time   → string with a unit: "1/4", "1/8." (dotted), "1/8t" (triplet), "3 beats",
           "2 bars", "250ms", "3.5s"
  level  → number in dB, or the string "-inf"
  shape  → linear | equal_power | exp | log | hold   ("qsin" accepted as equal_power)
"""

import math
import re
from typing import Annotated, Literal, Union

import numpy as np
from pydantic import AfterValidator, BeforeValidator

_NOTE = re.compile(r"^(\d+)/(\d+)([.t]?)$")
_COUNT = re.compile(r"^(\d+(?:\.\d+)?)\s*(beat|beats|bar|bars)$")
_CLOCK = re.compile(r"^(\d+(?:\.\d+)?)\s*(ms|s)$")
_POW2 = {1, 2, 4, 8, 16, 32, 64}

TIME_HELP = (
    'time must be a string with a unit, e.g. "1/4", "1/8." (dotted), "1/8t" (triplet), '
    '"3 beats", "2 bars", "250ms", "3.5s"'
)


def check_time(value: object) -> str:
    """Syntax check only (no tempo needed). Returns the normalized string."""
    if not isinstance(value, str):
        raise ValueError(f"{TIME_HELP}; got {value!r}")
    s = value.strip().lower()
    if _CLOCK.match(s) or _COUNT.match(s):
        return s
    m = _NOTE.match(s)
    if m:
        if int(m.group(2)) not in _POW2:
            raise ValueError(f"note value {value!r}: denominator must be 1, 2, 4, 8, 16, 32 or 64")
        return s
    raise ValueError(f"{TIME_HELP}; got {value!r}")


def parse_time(value: str, bpm: float, beats_per_bar: int = 4) -> float:
    """Resolve a time string to seconds at the given tempo."""
    s = check_time(value)
    beat = 60.0 / bpm
    if m := _CLOCK.match(s):
        n = float(m.group(1))
        return n / 1000.0 if m.group(2) == "ms" else n
    if m := _COUNT.match(s):
        n = float(m.group(1))
        return n * beat * (beats_per_bar if m.group(2).startswith("bar") else 1)
    m = _NOTE.match(s)
    assert m is not None
    beats = 4.0 * int(m.group(1)) / int(m.group(2))  # quarter note = 1 beat
    if m.group(3) == ".":
        beats *= 1.5
    elif m.group(3) == "t":
        beats *= 2.0 / 3.0
    return beats * beat


def _check_level(value: object) -> Union[float, str]:
    if isinstance(value, str):
        if value.strip().lower() == "-inf":
            return "-inf"
        raise ValueError(f'level must be a number in dB or "-inf"; got {value!r}')
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'level must be a number in dB or "-inf"; got {value!r}')
    return float(value)


def level_db(value: Union[float, str]) -> float:
    return -math.inf if value == "-inf" else float(value)


def db_to_gain(value: Union[float, str]) -> float:
    db = level_db(value)
    return 0.0 if db == -math.inf else 10 ** (db / 20.0)


Shape = Literal["linear", "equal_power", "exp", "log", "hold"]


def _normalize_shape(value: object) -> object:
    return "equal_power" if value == "qsin" else value


TimeStr = Annotated[str, AfterValidator(check_time)]
Level = Annotated[Union[float, str], BeforeValidator(_check_level)]
ShapeName = Annotated[Shape, BeforeValidator(_normalize_shape)]


def ramp_in(shape: str, n: int) -> np.ndarray:
    """Gain curve 0→1 over n samples. Fade-outs use the mirror: ramp_in(shape, n)[::-1]."""
    if n <= 0:
        return np.zeros(0)
    t = np.linspace(0.0, 1.0, n)
    match shape:
        case "linear":
            return t
        case "equal_power":
            return np.sin(t * np.pi / 2)
        case "exp":
            return t**2
        case "log":
            return np.sqrt(t)
        case "hold":
            return np.ones(n)
    raise ValueError(f"unknown shape {shape!r}")
