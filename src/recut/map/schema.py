"""
schema.py — Types for the music map pipeline (v4)

Input types (from analysis pipeline JSON): TypedDict — raw dicts at runtime.
Output types (MusicMap and friends): Pydantic BaseModel — validation + serialization.
"""

from pathlib import Path
from typing import Literal, NewType, Optional

from pydantic import BaseModel
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


class EnrichedSegment(BaseModel):
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


class MusicMap(BaseModel):
    path: str
    bpm: float
    beats_per_bar: int
    duration: float
    beats: list[BeatTime]
    bars: list[BeatTime]
    segments: list[EnrichedSegment]
    sources: Sources
    meta: Meta
    key: Optional[KeySignature] = None  # None for maps predating key detection
