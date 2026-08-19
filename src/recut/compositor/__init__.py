import numpy as np

from recut.audio import Audio
from recut.compositor.nodes import Clip, Node
from recut.map.parser import bars_to_seconds, beats_to_seconds, get_segment
from recut.map.schema import MusicMap
from recut.primitives.cut import cut

# Re-export so existing callers (`from recut.compositor import Clip, Loop`) keep working
__all__ = ["Clip", "Node", "compose"]


def compose(music_map: MusicMap, audio: Audio, *nodes: Node) -> Audio:
    """
    Execute a sequence of edit nodes against an audio file.

    Validate before calling if needed:
        results = validate(music_map, *nodes)

    Example:
        compose(music_map, audio, Clip("verse"), Clip("chorus", loop=2))
    """
    composition = []

    for node in nodes:
        segment = get_segment(music_map, node.segment_name, node.index)

        if node.snap_to_downbeat and segment.downbeats:
            start = segment.downbeats[0]
            end = segment.downbeats[-1]
        else:
            start = segment.start
            end = segment.end

        if node.offset_bars is not None:
            start += bars_to_seconds(music_map, node.offset_bars)
        elif node.offset_beats is not None:
            start += beats_to_seconds(music_map, node.offset_beats)

        if node.bars is not None:
            end = start + bars_to_seconds(music_map, node.bars)
            if end > segment.end:
                raise ValueError(f"{node.bars} bars exceeds segment length for {node.segment_name!r}")
        elif node.beats is not None:
            end = start + beats_to_seconds(music_map, node.beats)
            if end > segment.end:
                raise ValueError(f"{node.beats} beats exceeds segment length for {node.segment_name!r}")

        clip = cut(start, end)(audio)

        if node.loop is not None:
            clip = Audio(np.concatenate([clip.samples] * node.loop, axis=-1), audio.sr)

        for effect in node.fx:
            clip = effect(clip)

        composition.append(clip)

    return Audio(np.concatenate([a.samples for a in composition], axis=-1), audio.sr)
