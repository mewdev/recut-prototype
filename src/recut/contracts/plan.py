"""plan.json v2 — Ableton-style session (PLAN §3.2). Frozen contract: change PLAN.md first."""

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from recut.contracts.units import Level, ShapeName, TimeStr
from recut.map.schema import SegmentName


class _Strict(BaseModel):
    # extra="forbid": a typo in a field name is an error, not silently ignored.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SourceRef(_Strict):
    file: str
    map: str


class FadeHandle(_Strict):
    length: TimeStr
    shape: ShapeName = "equal_power"


# ---- devices (Ableton names) ------------------------------------------------


class Utility(_Strict):
    type: Literal["utility"]
    id: str
    gain: Level = 0.0
    width: float = Field(100.0, ge=0, le=200)


class EqBand(_Strict):
    frequency: float = Field(gt=0)
    gain: float = 0.0
    q: float = Field(0.71, gt=0)


class Eq(_Strict):
    type: Literal["eq"]
    id: str
    low_cut: Optional[float] = Field(None, gt=0)
    high_cut: Optional[float] = Field(None, gt=0)
    bands: list[EqBand] = []


class AutoFilter(_Strict):
    type: Literal["auto_filter"]
    id: str
    filter: Literal["lowpass", "highpass", "bandpass"] = "lowpass"
    frequency: float = Field(20000.0, gt=0)
    resonance: float = Field(0.0, ge=0, le=1.25)


class Reverb(_Strict):
    type: Literal["reverb"]
    id: str
    decay: TimeStr = "2s"
    pre_delay: TimeStr = "0ms"
    size: float = Field(50.0, ge=0, le=100)
    hi_cut: float = Field(8000.0, gt=0)
    width: float = Field(100.0, ge=0, le=100)
    dry_wet: float = Field(100.0, ge=0, le=100)


class Delay(_Strict):
    type: Literal["delay"]
    id: str
    time: TimeStr = "1/8"
    feedback: float = Field(30.0, ge=0, le=95)
    ping_pong: bool = False
    filter_lo: float = Field(100.0, gt=0)
    filter_hi: float = Field(8000.0, gt=0)
    dry_wet: float = Field(100.0, ge=0, le=100)


class Limiter(_Strict):
    type: Literal["limiter"]
    id: str
    ceiling: float = Field(-1.0, le=0)


Device = Annotated[Union[Utility, Eq, AutoFilter, Reverb, Delay, Limiter], Field(discriminator="type")]

# ---- automation ---------------------------------------------------------------

AutoValue = Level  # dB for gain/sends, raw parameter units for device params ("-inf" allowed)


class Ramp(_Strict):
    target: str
    from_: AutoValue = Field(alias="from")
    to: AutoValue
    over: TimeStr
    at: Union[Literal["start", "end"], TimeStr] = "start"
    shape: ShapeName = "linear"


class Points(_Strict):
    target: str
    points: list[tuple[TimeStr, AutoValue]] = Field(min_length=2)
    shape: ShapeName = "linear"


Automation = Union[Ramp, Points]

# ---- arrangement ----------------------------------------------------------------


class ClipNode(_Strict):
    type: Literal["clip"]
    id: str
    source: str
    segment: SegmentName
    index: int = Field(1, ge=1)
    bars: Optional[float] = Field(None, gt=0)
    beats: Optional[float] = Field(None, gt=0)
    offset_bars: Optional[float] = Field(None, ge=0)
    offset_beats: Optional[float] = Field(None, ge=0)
    loop: Optional[int] = Field(None, ge=1)
    gain: Level = 0.0
    fade_in: Optional[FadeHandle] = None
    fade_out: Optional[FadeHandle] = None
    devices: list[Device] = []
    sends: dict[str, Level] = {}
    automation: list[Automation] = []

    @model_validator(mode="after")
    def _exclusive(self):
        if self.bars is not None and self.beats is not None:
            raise ValueError(f"clip {self.id}: set bars OR beats, not both")
        if self.offset_bars is not None and self.offset_beats is not None:
            raise ValueError(f"clip {self.id}: set offset_bars OR offset_beats, not both")
        return self


class XFadeNode(_Strict):
    type: Literal["xfade"]
    id: str
    length: TimeStr = "500ms"
    shape: ShapeName = "equal_power"
    out_shape: Optional[ShapeName] = None
    in_shape: Optional[ShapeName] = None

    @property
    def shape_out(self) -> str:
        return self.out_shape or self.shape

    @property
    def shape_in(self) -> str:
        return self.in_shape or self.shape


Node = Annotated[Union[ClipNode, XFadeNode], Field(discriminator="type")]


class Track(_Strict):
    id: str
    volume: Level = 0.0
    pan: float = Field(0.0, ge=-50, le=50)
    devices: list[Device] = []
    automation: list[Automation] = []
    clips: list[Node] = Field(min_length=1)


class ReturnTrack(_Strict):
    id: str
    name: str = ""
    volume: Level = 0.0
    devices: list[Device] = []
    automation: list[Automation] = []


def _default_master_devices() -> list:
    return [Limiter(type="limiter", id="lim", ceiling=-1.0)]


class Master(_Strict):
    devices: list[Device] = Field(default_factory=_default_master_devices)


class Plan(_Strict):
    version: Literal[2]
    sources: dict[str, SourceRef] = Field(min_length=1)
    returns: list[ReturnTrack] = []
    tracks: list[Track] = Field(min_length=1)
    master: Master = Field(default_factory=Master)
    target_duration_s: Optional[float] = Field(None, gt=0)
    notes: Optional[str] = None  # free text: anything the format can't express yet

    @model_validator(mode="after")
    def _references(self):
        ids: set[str] = set()
        return_ids = {r.id for r in self.returns}

        def unique(i: str) -> None:
            if i in ids:
                raise ValueError(f"duplicate id {i!r}")
            ids.add(i)

        for r in self.returns:
            for d in r.devices:
                unique(d.id)
        for t in self.tracks:
            for d in t.devices:
                unique(d.id)
            nodes = t.clips
            if not isinstance(nodes[0], ClipNode) or not isinstance(nodes[-1], ClipNode):
                raise ValueError(f"track {t.id}: must start and end with a clip, not an xfade")
            for prev, cur in zip(nodes, nodes[1:]):
                if isinstance(prev, XFadeNode) and isinstance(cur, XFadeNode):
                    raise ValueError(f"track {t.id}: two xfades next to each other ({prev.id}, {cur.id})")
            for n in nodes:
                unique(n.id)
                if isinstance(n, ClipNode):
                    if n.source not in self.sources:
                        raise ValueError(f"clip {n.id}: unknown source {n.source!r}")
                    for key in n.sends:
                        if key not in return_ids:
                            raise ValueError(f"clip {n.id}: send to unknown return {key!r}")
                    for d in n.devices:
                        unique(d.id)
        return self
