from dataclasses import dataclass
from typing import Callable, Optional

from compositor import Node
from map_parser import MapParser
from validator.checks import check_duration_exceeds, check_label_exists
from validator.types import ValidationResult


@dataclass
class Rule:
    name: str
    check: Callable[[Node, MapParser], Optional[ValidationResult]]


RULES = [
    Rule(name="label_exists", check=check_label_exists),
    Rule(name="duration_exceeds", check=check_duration_exceeds),
]
