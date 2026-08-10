from dataclasses import dataclass
from typing import Literal

from nodes import Node

Severity = Literal["error", "warning", "info"]

@dataclass
class ValidationResult:
    severity: Severity
    message: str
    node: Node
