from dataclasses import dataclass
from typing import Literal

from recut.compositor.nodes import Node

Severity = Literal["error", "warning", "info"]


@dataclass
class ValidationResult:
    severity: Severity
    message: str
    node: Node
