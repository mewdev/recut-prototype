from typing import Optional

from compositor import Node
from map_parser import MapParser
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
