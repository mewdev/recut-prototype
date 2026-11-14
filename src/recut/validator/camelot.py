"""Camelot wheel helper for the `key_compat` linter rule."""

from typing import Optional

_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pitch_class(tonic: str) -> Optional[int]:
    t = tonic.strip()
    if not t or t[0].upper() not in _PC:
        return None
    pc = _PC[t[0].upper()]
    for ch in t[1:]:
        if ch in "#♯":
            pc += 1
        elif ch in "b♭":
            pc -= 1
        else:
            return None
    return pc % 12


def camelot(tonic: str, mode: str) -> Optional[tuple[int, str]]:
    """(number 1-12, 'A' minor | 'B' major), e.g. ("F#", "minor") -> (11, "A"); None if unknown."""
    pc = pitch_class(tonic)
    m = mode.strip().lower()
    if pc is None or m not in ("major", "maj", "minor", "min"):
        return None
    if m.startswith("maj"):
        return (8 + 7 * pc - 1) % 12 + 1, "B"
    return (8 + 7 * ((pc + 3) % 12) - 1) % 12 + 1, "A"


def keys_compatible(a: tuple[int, str], b: tuple[int, str]) -> bool:
    """Same key, relative major/minor (same number), or one step round the wheel."""
    if a[1] == b[1]:
        return (a[0] - b[0]) % 12 in (0, 1, 11)
    return a[0] == b[0]
