"""
Compositor node types — kept separate so both compositor and validator
can import them without a circular dependency.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from recut.map.schema import SegmentName


@dataclass
class Clip:
    """Extract one occurrence of a labeled segment."""

    segment_name: SegmentName
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
    loop: Optional[int] = None
    fx: list[Callable] = field(default_factory=list)
    # fx: effects applied to the clip after cutting, in order.
    # Each effect is a callable: Audio -> Audio (curried primitive).


Node = Clip
