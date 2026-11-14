"""
schema.py — Types for the music map pipeline (v4)

Input types (from analysis pipeline JSON): TypedDict — raw dicts at runtime.
Output types (MusicMap and friends): Pydantic BaseModel — validation + serialization.
"""

from pathlib import Path
from typing import Literal, NewType, Optional

from pydantic import BaseModel, field_validator
from typing_extensions import TypedDict

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

NATURAL_ROOTS = ["C", "D", "E", "F", "G", "A", "B"]
SHARP_ROOTS = ["C#", "D#", "F#", "G#", "A#"]
FLAT_ROOTS = ["Db", "Eb", "Gb", "Ab", "Bb"]
ROOTS = NATURAL_ROOTS + SHARP_ROOTS + FLAT_ROOTS


def _load_chord_vocab(vocab: str = "full") -> frozenset:
    path = Path(__file__).parent / f"data/{vocab}_chord_list.txt"
    lines = path.read_text().splitlines()
    chords = {"N"}
    for line in lines:
        quality = line.removeprefix("C:")
        for root in ROOTS:
            chords.add(f"{root}:{quality}")
    return frozenset(chords)


VALID_CHORDS = _load_chord_vocab("full")

ChordStr = NewType("ChordStr", str)


def is_valid_chord(s: str) -> bool:
    return s in VALID_CHORDS


# ---------------------------------------------------------------------------
# INPUT TYPES  (what ChordMini gives us — TypedDicts, plain dicts at runtime)
# ---------------------------------------------------------------------------

BeatTime = float
BeatsPerBar = int  # what madmom's DBN actually detects

SegmentName = Literal[
    "intro",
    "verse",
    "pre-chorus",
    "chorus",
    "bridge",
    "inst",
    "outro",
    "silence",
    "interlude",
    "ending",
]


class ChordEntry(TypedDict):
    start: float
    end: float
    chord: ChordStr


class RawSegment(TypedDict):
    start: float
    end: float
    label: SegmentName


class AnalysisSources(TypedDict):
    beats: str
    chords: str
    structure: str
    key: str


class RawAnalysis(TypedDict):
    path: str
    bpm: int
    beats_per_bar: BeatsPerBar
    beats: list[BeatTime]
    downbeats: list[BeatTime]
    segments: list[RawSegment]
    chords: list[ChordEntry]
    key: str  # e.g. "F# minor" — madmom's key_prediction_to_label() format
    _sources: AnalysisSources


# ---------------------------------------------------------------------------
# OUTPUT TYPES  (what our map produces — Pydantic BaseModel)
# ---------------------------------------------------------------------------

class KeySignature(BaseModel):
    tonic: str
    mode: str


# Loudness of digital silence (and of a zero-length segment): 20*log10(1e-10).
# Never NaN: NaN is not valid JSON and breaks browsers reading the map.
LOUDNESS_FLOOR_DB = -200.0


class EnrichedSegment(BaseModel):
    """One section of the song.

    Start/end rules (so no audio is lost at the edges):
    - `start` snaps to the nearest downbeat, except the FIRST segment, which starts at 0.0:
      a pickup / lead-in before the first downbeat belongs to it. Then `downbeats[0] > start`.
      `bars`/`downbeats`/`phrases` count only real downbeats, so the lead-in is not a bar, and
      clip `offset_bars` / `offset_beats` count from `downbeats[0]`, not from `start`
      (engine._clip_bounds).
    - `end` snaps to the nearest downbeat, except the LAST segment, which runs to the end of
      the audio (fade-out / trailing silence).
    - Segments that would be zero-length are not created.
    """

    index: int
    segment_name: SegmentName
    start: float
    end: float
    duration: float
    bars: int
    downbeats: list[BeatTime]
    phrases: list[BeatTime]
    chords: list[ChordEntry]
    # TODO: add lufs_integrated: float once pyloudnorm integrated (see todo-and-ideas.md)
    loudness_db: float
    loudness_db_start: float
    loudness_db_end: float
    # summaries of the optional time series on MusicMap (None when the map predates them)
    pace: Optional[float] = None  # mean normalized pace (0-1) over [start, end)
    drum_activity: Optional[float] = None  # mean drum activity (0-1); filled by M1 (Demucs)
    vocal_activity: Optional[float] = None  # mean vocal activity (0-1); filled by M1 (Demucs)

    @field_validator("loudness_db", "loudness_db_start", "loudness_db_end", mode="before")
    @classmethod
    def _no_nan_loudness(cls, v):
        # maps written before M0 hold NaN for empty segments; load them as the floor
        if isinstance(v, float) and v != v:
            return LOUDNESS_FLOOR_DB
        return v


class ModelRef(BaseModel):
    name: str
    version: str


class Sources(BaseModel):
    beats: ModelRef
    chords: ModelRef
    structure: ModelRef
    key: Optional[ModelRef] = None  # None for maps predating key detection


class Meta(BaseModel):
    audio_hash: str
    generated_at: str
    map_version: str


class Pace(BaseModel):
    """Onset density over time. Sample i is centred on t = i * hop_s (window 4 s, clipped at the
    track edges). `normalized` = events_per_min / the track's own 95th percentile, clipped to 0-1."""

    hop_s: float = 1.0
    events_per_min: list[float]
    normalized: list[float]


class LoudnessShortTerm(BaseModel):
    """EBU R128 short-term loudness (3 s window, ungated). Sample i is centred on t = i * hop_s.
    Floor -70 LUFS (silence); never -inf, which is not valid JSON."""

    hop_s: float = 1.0
    lufs: list[float]


class KeyRange(BaseModel):
    start: float
    end: float
    tonic: str
    mode: str


class StemActivity(BaseModel):
    hop_s: float = 0.1
    values: list[float]  # 0-1
    ranges: list[tuple[float, float]] = []  # spans where activity stays above the threshold


class InstrumentActivity(BaseModel):
    """Per-stem activity (M1, Demucs). Defined here, not filled yet."""

    drum: Optional[StemActivity] = None
    bass: Optional[StemActivity] = None
    vocal: Optional[StemActivity] = None
    other: Optional[StemActivity] = None


class MusicMap(BaseModel):
    path: str
    bpm: float  # derived from the beat grid (median inter-beat interval); see map/tempo.py
    bpm_raw: Optional[float] = None  # the tempo estimator's value when it disagreed (half-time)
    beats_per_bar: int
    duration: float
    beats: list[BeatTime]
    bars: list[BeatTime]
    segments: list[EnrichedSegment]
    sources: Sources
    meta: Meta
    key: Optional[KeySignature] = None  # None for maps predating key detection
    # M2/M3: optional time series, so maps made before them keep loading
    pace: Optional[Pace] = None
    loudness_short_term: Optional[LoudnessShortTerm] = None
    key_ranges: Optional[list[KeyRange]] = None
    instrument_activity: Optional[InstrumentActivity] = None  # M1: not computed yet
    # which method produced each optional field, e.g. {"pace": "librosa-onsets"}
    analysis_sources: Optional[dict[str, str]] = None
