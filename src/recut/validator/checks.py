from typing import Optional

from recut.compositor.nodes import Node
from recut.map.parser import (
    bars_to_seconds,
    beats_to_seconds,
    first_segment,
    get_segment,
    last_segment,
)
from recut.map.schema import MusicMap
from recut.validator.types import ValidationResult


def check_label_exists(node: Node, music_map: MusicMap) -> Optional[ValidationResult]:
    try:
        get_segment(music_map, node.segment_name, node.index)
    except ValueError as error:
        return ValidationResult(severity="error", message=str(error), node=node)
    return None


def check_duration_exceeds(node: Node, music_map: MusicMap) -> Optional[ValidationResult]:
    try:
        segment = get_segment(music_map, node.segment_name, node.index)
    except ValueError:
        return None
    if node.bars is not None:
        requested_s = bars_to_seconds(music_map, node.bars)
        segment_duration_s = segment.end - segment.start
        if segment.start + requested_s > segment.end:
            return ValidationResult(
                severity="error",
                message=f"{node.bars} bars ({requested_s:.2f}s) exceeds '{node.segment_name}' segment duration ({segment_duration_s:.2f}s)",
                node=node,
            )
    elif node.beats is not None:
        requested_s = beats_to_seconds(music_map, node.beats)
        segment_duration_s = segment.end - segment.start
        if segment.start + requested_s > segment.end:
            return ValidationResult(
                severity="error",
                message=f"{node.beats} beats ({requested_s:.2f}s) exceeds '{node.segment_name}' segment duration ({segment_duration_s:.2f}s)",
                node=node,
            )
    return None


def check_sequence_boundaries(nodes: list[Node], music_map: MusicMap) -> list[ValidationResult]:
    if not nodes:
        return []
    results: list[ValidationResult] = []
    first_song_seg = first_segment(music_map)
    last_song_seg = last_segment(music_map)
    first_node = nodes[0]

    try:
        seg = get_segment(music_map, first_node.segment_name, first_node.index)
        if abs(seg.start - first_song_seg.start) > 0.1:
            results.append(
                ValidationResult(
                    severity="warning",
                    message=(
                        f"Cut starts at {first_node.segment_name!r} (t={seg.start:.2f}s) "
                        f"but song begins at {first_song_seg.segment_name!r} (t={first_song_seg.start:.2f}s). "
                        "Hard cut at start will sound abrupt — apply an effect (e.g. fade-in, reverb tail) to smooth the entry."
                    ),
                    node=first_node,
                )
            )
    except ValueError:
        pass
    last_node = nodes[-1]
    try:
        seg = get_segment(music_map, last_node.segment_name, last_node.index)
        if abs(seg.end - last_song_seg.end) > 0.1:
            results.append(
                ValidationResult(
                    severity="warning",
                    message=(
                        f"Cut ends at {last_node.segment_name!r} (t={seg.end:.2f}s) "
                        f"but song ends at {last_song_seg.segment_name!r} (t={last_song_seg.end:.2f}s). "
                        "Hard cut at end will sound abrupt — apply an effect (e.g. fade-out, reverb tail) to smooth the exit."
                    ),
                    node=last_node,
                )
            )
    except ValueError:
        pass
    return results
