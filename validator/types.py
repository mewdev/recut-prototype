from dataclasses import dataclass
from typing import Literal

from compositor import Node


Severity = Literal["error", "warning", "info"]

@dataclass
class ValidationResult:
    severity: Severity
    message: str
    node: Node
