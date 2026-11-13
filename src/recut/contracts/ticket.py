"""Ticket folder files (PLAN §3.1, §3.5)."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

TicketStatus = Literal[
    "new", "in_progress", "in_review", "needs_rework", "shipped", "client_approved", "client_changes"
]

Tag = Literal[
    "intent_misread",
    "wrong_section",
    "off_beat",
    "harmonic_clash",
    "energy_drop",
    "abrupt",
    "bad_ending",
    "duration_miss",
    "artifact",
    "map_wrong",
    "missing_primitive",
    "fx_wrong",
]
TAGS: tuple[str, ...] = Tag.__args__  # type: ignore[attr-defined]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Request(_Strict):
    id: str
    created_at: str
    text: str
    target_duration_s: Optional[float] = None
    client_name: Optional[str] = None
    client_contact: Optional[str] = None
    files: dict[str, str] = {}  # source id → original upload filename
    status: TicketStatus = "new"


class SessionMeta(_Strict):
    started_at: str
    agent: Optional[str] = None
    model: Optional[str] = None
    recut_git_sha: Optional[str] = None


class Intent(_Strict):
    target_duration_s: Optional[float] = None
    must_keep: list[str] = []
    must_cut: list[str] = []
    ending: Optional[str] = None
    notes: Optional[str] = None


class SpliceReview(_Strict):
    ok: bool
    tags: list[Tag] = []
    note: Optional[str] = None


class Review(_Strict):
    iteration: int = Field(ge=1)
    verdict: Literal["ship", "fixable", "reject"]
    splices: dict[str, SpliceReview] = {}
    tags: list[Tag] = []
    note: Optional[str] = None
    reviewed_at: Optional[str] = None


class Share(_Strict):
    token: str
    session: int
    iteration: int
    created_at: str
    client_decision: Optional[Literal["approved", "changes"]] = None
    client_note: Optional[str] = None
