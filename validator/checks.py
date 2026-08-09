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
