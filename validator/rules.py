from dataclasses import dataclass
from typing import Callable, Optional

from map_parser import MapParser
from nodes import Node
from validator.checks import check_duration_exceeds, check_label_exists, check_sequence_boundaries
from validator.types import ValidationResult


@dataclass
class Rule:
    name: str
    check: Callable[[Node, MapParser], Optional[ValidationResult]]


@dataclass
class SequenceRule:
    """Check that runs against the full node list, not a single node."""

    name: str
    check: Callable[[list[Node], MapParser], list[ValidationResult]]


RULES: list[Rule] = [
    Rule(name="label_exists", check=check_label_exists),
    Rule(name="duration_exceeds", check=check_duration_exceeds),
]

SEQUENCE_RULES: list[SequenceRule] = [
    SequenceRule(name="sequence_boundaries", check=check_sequence_boundaries),
]
