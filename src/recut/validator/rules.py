from dataclasses import dataclass
from typing import Callable, Optional

from recut.compositor.nodes import Clip
from recut.map.schema import MusicMap
from recut.validator.checks import (
    check_duration_exceeds,
    check_label_exists,
    check_sequence_boundaries,
)
from recut.validator.types import ValidationResult


@dataclass
class Rule:
    name: str
    check: Callable[[Clip, MusicMap], Optional[ValidationResult]]


@dataclass
class SequenceRule:
    """Check that runs against the full node list, not a single node."""

    name: str
    check: Callable[[list[Clip], MusicMap], list[ValidationResult]]


RULES: list[Rule] = [
    Rule(name="label_exists", check=check_label_exists),
    Rule(name="duration_exceeds", check=check_duration_exceeds),
]

SEQUENCE_RULES: list[SequenceRule] = [
    SequenceRule(name="sequence_boundaries", check=check_sequence_boundaries),
]
