from dataclasses import dataclass
from typing import Optional, Union

import numpy as np

from audio import Audio
from map_parser import MapParser
from primitives.cut import cut


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


def compose(parser: MapParser, audio_path: str, *nodes: Node) -> Audio:
    """
    Execute a sequence of edit nodes against an audio file.

    Example:
        compose(parser, "song.mp3", Clip("verse"), Loop("chorus", times=2))
    """
    audio = Audio.load(audio_path)
    composition = []

    for node in nodes:
        segment = parser.get_segment(node.label, node.index)

        if node.snap_to_downbeat and "audio_start" in segment:
            start = segment["audio_start"]
            end = segment["audio_end"]
        else:
            start = segment["start"]
            end = segment["end"]
        # apply offset — shift start forward by N bars/beats
        if node.offset_bars is not None:
            start += parser.bars_to_seconds(node.offset_bars)
        elif node.offset_beats is not None:
            start += parser.beats_to_seconds(node.offset_beats)

        if node.bars is not None:
            end = start + parser.bars_to_seconds(node.bars)
            if end > segment["end"]:
                raise ValueError(f"{node.bars} bars exceeds segment length for {node.label!r}")
        elif node.beats is not None:
            end = start + parser.beats_to_seconds(node.beats)
            if end > segment["end"]:
                raise ValueError(f"{node.beats} beats exceeds segment length for {node.label!r}")
        clip = cut(start, end)(audio)

        if isinstance(node, Loop):
            loop = [clip] * (node.times)
            composition.extend(loop)

        else:
            composition.append(clip)

    return Audio(np.concatenate([a.samples for a in composition], axis=-1), audio.sr)
