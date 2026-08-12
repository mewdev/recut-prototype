import numpy as np

from audio import Audio
from compositor.nodes import Clip, Loop, Node
from map.parser import MapParser
from primitives.cut import cut
from validator import validate

# Re-export so existing callers (`from compositor import Clip, Loop`) keep working
__all__ = ["Clip", "Loop", "Node", "compose"]


def compose(
    parser: MapParser, audio_path: str, *nodes: Node, skip_validation: bool = False
) -> Audio:
    """
    Execute a sequence of edit nodes against an audio file.

    Validates all nodes before rendering. Raises ValueError on any error.
    Pass skip_validation=True only when you have already validated externally.

    Example:
        compose(parser, "song.mp3", Clip("verse"), Loop("chorus", times=2))
    """
    if not skip_validation:
        results = validate(parser, *nodes)
        errors = [r for r in results if r.severity == "error"]
        warnings = [r for r in results if r.severity == "warning"]
        if errors or warnings:
            msgs = "\n".join(
                f"  [{r.severity.upper()}] [{r.node.label}] {r.message}" for r in errors + warnings
            )
            raise ValueError(
                f"Composition blocked ({len(errors)} error(s), {len(warnings)} warning(s)):\n{msgs}"
            )

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
            clip = Audio(np.concatenate([clip.samples] * node.times, axis=-1), audio.sr)

        for effect in node.fx:
            clip = effect(clip)

        composition.append(clip)

    return Audio(np.concatenate([a.samples for a in composition], axis=-1), audio.sr)
