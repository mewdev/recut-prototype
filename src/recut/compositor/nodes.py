"""
Compositor node types — kept separate so both compositor and validator
can import them without a circular dependency.
"""

from dataclasses import dataclass, field
from typing import Optional, Union

from recut.compositor.effects import Effect
from recut.map.schema import SegmentName
from recut.primitives.curves import Curve


@dataclass
class Clip:
    """Extract one occurrence of a labeled segment."""

    segment_name: SegmentName
    index: int = 1
    source: Optional[str] = None
    # source: key into the sources dict passed to compose().
    # None = use the single default source (backward compatible).
    # Named sources enable multi-file compositions (two songs, parallel tracks, etc.)
    bars: Optional[float] = None
    beats: Optional[float] = None
    offset_bars: Optional[float] = None
    offset_beats: Optional[float] = None
    # offset_bars/offset_beats: skip N bars/beats from segment start before cutting.
    # Use to splice into the middle of a segment, e.g. take only the second half
    # of a chorus: Clip("chorus", offset_beats=16, beats=16)
    snap_to_downbeat: bool = False
    # snap_to_downbeat: use downbeats[0]/downbeats[-1] as start/end instead of
    # segment.start/segment.end. Fixes pre-roll silence when the structural model
    # draws the section boundary slightly before the first actual beat (common on
    # intros/pickups).
    # Don't use when the segment genuinely starts before the first downbeat
    # (e.g. chorus pickups) — snapping will skip real audio.
    # CAUTION on the END side: downbeats[-1] is the LAST BAR'S START, not the
    # segment's end — if a segment's downbeats array doesn't include a trailing
    # marker at segment.end (common when a segment has N bars but only N downbeat
    # timestamps), this silently drops the final bar's worth of audio. Check
    # `segment.end - segment.downbeats[-1]` before using this on a segment you
    # need the tail of; if it's ~1 bar, snap_to_downbeat will cut it off.
    loop: Optional[int] = None
    fx: list[Effect] = field(default_factory=list)


@dataclass
class XFade:
    """Crossfade directive — place between two audio nodes to join them with a crossfade.

    ms    : crossfade duration in milliseconds
    curve : fade shape — "linear" | "log" | "exp" | "qsin"
              qsin gives equal-power crossfade — best default for music
    """

    ms: float = 500.0
    curve: Curve = "qsin"
    beats: Optional[float] = None
    # beats: if set, compositor resolves duration from map BPM instead of using ms.


AudioNode = Clip

Node = Union[Clip, XFade]
