"""render.json (PLAN §3.3) — what the GUI needs to draw "what the cut did"."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RenderSegment(BaseModel):
    node_id: str
    source: str
    label: str
    src_start: float
    src_end: float
    out_start: float
    out_end: float


class Splice(BaseModel):
    id: str
    out_time: float
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    cross_source: bool
    overlap_ms: float = 0.0
    out_shape: Optional[str] = None
    in_shape: Optional[str] = None


class Issue(BaseModel):
    severity: Literal["error", "warn", "info"]
    rule: str
    message: str
    splice: Optional[str] = None
    node: Optional[str] = None


class SourceInfo(BaseModel):
    bpm: float
    key: Optional[str] = None
    duration_s: float
    lufs_in: Optional[float] = None
    lufs_target: Optional[float] = None


class AutomationSpan(BaseModel):
    node_id: str
    target: str
    out_start: float
    out_end: float


class RenderInfo(BaseModel):
    duration_s: float
    segments: list[RenderSegment]
    splices: list[Splice]
    issues: list[Issue] = []
    sources: dict[str, SourceInfo] = {}
    automation: list[AutomationSpan] = []
    returns_tail_end: Optional[float] = None
    peak_dbfs: float
    limiter_applied: bool = False

    def to_json(self) -> dict:
        return self.model_dump(by_alias=True)
