from dataclasses import dataclass
from typing import Literal, Optional

from recut.compositor.nodes import Clip

Severity = Literal["error", "warning", "info"]


@dataclass
class ValidationResult:
    severity: Severity
    message: str
    node: Clip
    source: Optional[str] = None
    # source: which audio source this result refers to.
    # None = single-source composition (default). Set when multi-source compositions exist.
