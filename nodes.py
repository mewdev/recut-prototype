"""
Compositor node types — kept separate so both compositor and validator
can import them without a circular dependency.
"""

from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class Clip:
    """Extract one occurrence of a labeled segment."""

    label: str
    index: int = 1
    bars: Optional[float] = None
    beats: Optional[float] = None
    offset_bars: Optional[float] = None
    offset_beats: Optional[float] = None
    # offset_bars/offset_beats: skip N bars/beats from segment start before cutting.
    # Use to splice into the middle of a segment, e.g. take only the second half
    # of a chorus: Clip("chorus", offset_beats=16, beats=16)
    snap_to_downbeat: bool = False
    # snap_to_downbeat: use downbeats[0] as start instead of segment["start"].
    # Fixes pre-roll silence when the structural model draws the section boundary
    # slightly before the first actual beat (common on intros/pickups).
    # Don't use when the segment genuinely starts before the first downbeat
    # (e.g. chorus pickups) — snapping will skip real audio.


@dataclass
class Loop:
    """Extract a segment and repeat it N times."""

    label: str
    times: int
    index: int = 1
    bars: Optional[float] = None
    beats: Optional[float] = None
    offset_bars: Optional[float] = None
    offset_beats: Optional[float] = None
    # offset_bars/offset_beats: same as Clip — skip N bars/beats from segment start.
    snap_to_downbeat: bool = False
    # snap_to_downbeat: same as Clip — use when looping a segment that has
    # pre-roll silence before the first beat, so the loop joins cleanly.


Node = Union[Clip, Loop]
