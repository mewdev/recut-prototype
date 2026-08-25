import numpy as np

from recut.audio import Audio
from recut.compositor.nodes import Clip, Node, XFade
from recut.map.parser import bars_to_seconds, beats_to_seconds, get_segment
from recut.map.schema import MusicMap
from recut.primitives.cut import cut
from recut.primitives.xfade import xfade

# Re-export so existing callers (`from recut.compositor import Clip, XFade`) keep working
__all__ = ["Clip", "XFade", "Node", "compose"]


def compose(music_map: MusicMap, audio: Audio, *nodes: Node) -> Audio:
    """
    Execute a sequence of edit nodes against an audio file.

    Validate before calling if needed:
        results = validate(music_map, *nodes)

    Example:
        compose(music_map, audio, Clip("verse"), Clip("chorus", loop=2))
    """
    composition = []
    pending_xfade = None  # set when an XFade node is encountered, consumed on next clip

    for node in nodes:
        if isinstance(node, XFade):
            if pending_xfade is not None:
                raise ValueError("Two XFades cannot be next to each other")
            pending_xfade = node
            continue

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
                raise ValueError(
                    f"{node.bars} bars exceeds segment length for {node.segment_name!r}"
                )
        elif node.beats is not None:
            end = start + beats_to_seconds(music_map, node.beats)
            if end > segment.end:
                raise ValueError(
                    f"{node.beats} beats exceeds segment length for {node.segment_name!r}"
                )

        clip = cut(start, end)(audio)

        if node.loop is not None:
            clip = Audio(np.concatenate([clip.samples] * node.loop, axis=-1), audio.sr)

        for effect in node.fx:
            clip = effect.to_fn()(clip)

        if pending_xfade is not None:
            if not composition:
                raise ValueError("XFade cannot be first node — nothing to crossfade into")
            prev = composition.pop()
            ms = (
                beats_to_seconds(music_map, pending_xfade.beats) * 1000
                if pending_xfade.beats is not None
                else pending_xfade.ms
            )
            clip = xfade(ms, pending_xfade.curve)(prev, clip)
            pending_xfade = None

        composition.append(clip)

    if pending_xfade is not None:
        raise ValueError("XFade cannot be last node — nothing to crossfade into")

    return Audio(np.concatenate([a.samples for a in composition], axis=-1), audio.sr)
