from typing import Optional

from map_parser import MapParser
from nodes import Node
from validator.types import ValidationResult


def check_label_exists(
    node: Node,
    parser: MapParser,
) -> Optional[ValidationResult]:
    try:
        parser.get_segment(node.label, node.index)
    except ValueError as error:
        return ValidationResult(severity="error", message=str(error), node=node)
    return None


def check_duration_exceeds(node: Node, parser: MapParser) -> Optional[ValidationResult]:
    try:
        segment = parser.get_segment(node.label, node.index)
    except ValueError:
        return None
    if node.bars is not None:
        requested_s = parser.bars_to_seconds(node.bars)
        segment_duration_s = segment["end"] - segment["start"]
        if segment["start"] + requested_s > segment["end"]:
            return ValidationResult(
                severity="error",
                message=f"{node.bars} bars ({requested_s:.2f}s) exceeds '{node.label}' segment duration ({segment_duration_s:.2f}s)",
                node=node,
            )
    elif node.beats is not None:
        requested_s = parser.beats_to_seconds(node.beats)
        segment_duration_s = segment["end"] - segment["start"]
        if segment["start"] + requested_s > segment["end"]:
            return ValidationResult(
                severity="error",
                message=f"{node.beats} beats ({requested_s:.2f}s) exceeds '{node.label}' segment duration ({segment_duration_s:.2f}s)",
                node=node,
            )
    return None


def check_sequence_boundaries(nodes: list[Node], parser: MapParser) -> list[ValidationResult]:
    """
    Warn when the cut doesn't start at the song's beginning or end at its last
    meaningful segment. A hard cut at either edge will sound abrupt — the fix is
    to apply a fade-in / fade-out effect before rendering.
    """
    if not nodes:
        return []

    results: list[ValidationResult] = []
    first_song_seg = parser.first_segment()
    last_song_seg = parser.last_segment()

    # check first node
    first_node = nodes[0]
    try:
        seg = parser.get_segment(first_node.label, first_node.index)
        if abs(seg["start"] - first_song_seg["start"]) > 0.1:
            results.append(ValidationResult(
                severity="warning",
                message=(
                    f"Cut starts at {first_node.label!r} (t={seg['start']:.2f}s) "
                    f"but song begins at {first_song_seg['label']!r} (t={first_song_seg['start']:.2f}s). "
                    "Hard cut at start will sound abrupt — apply an effect (e.g. fade-in, reverb tail) to smooth the entry."
                ),
                node=first_node,
            ))
    except ValueError:
        pass  # label_exists rule already catches this

    # check last node
    last_node = nodes[-1]
    try:
        seg = parser.get_segment(last_node.label, last_node.index)
        if abs(seg["end"] - last_song_seg["end"]) > 0.1:
            results.append(ValidationResult(
                severity="warning",
                message=(
                    f"Cut ends at {last_node.label!r} (t={seg['end']:.2f}s) "
                    f"but song ends at {last_song_seg['label']!r} (t={last_song_seg['end']:.2f}s). "
                    "Hard cut at end will sound abrupt — apply an effect (e.g. fade-out, reverb tail) to smooth the exit."
                ),
                node=last_node,
            ))
    except ValueError:
        pass

    return results
