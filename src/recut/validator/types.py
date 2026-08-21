from dataclasses import dataclass
from typing import Literal

from recut.compositor.nodes import AudioNode

Severity = Literal["error", "warning", "info"]


@dataclass
class ValidationResult:
    severity: Severity
    message: str
    node: AudioNode
