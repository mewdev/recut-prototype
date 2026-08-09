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


@dataclass
class Loop:
    """Extract a segment and repeat it N times."""
    label: str
    times: int
    index: int = 1
    bars: Optional[float] = None
    beats: Optional[float] = None


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

        start = segment.get("audio_start", segment["start"])
        end = segment.get("audio_end", segment["end"])
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
