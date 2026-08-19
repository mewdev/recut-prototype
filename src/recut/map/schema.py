"""
schema.py — TypedDicts and type aliases for the music map pipeline (v3)

Analysis pipeline (pipeline.py) is inspired by the ChordMini open-source toolchain:
beat tracking (BeatNet), chord recognition (Chord-CNN-LSTM), structure (SongFormer).
RawAnalysis mirrors the JSON output shape that pipeline produces.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NewType, Optional, TypedDict

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
# INPUT TYPES  (what ChordMini gives us)
# ---------------------------------------------------------------------------

BeatTime = float
TimeSignature = Literal["4/4"]

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


class RawAnalysis(TypedDict):
    path: str
    bpm: int
    time_signature: TimeSignature
    beats: list[BeatTime]
    downbeats: list[BeatTime]
    segments: list[RawSegment]
    chords: list[ChordEntry]
    _sources: AnalysisSources


# ---------------------------------------------------------------------------
# OUTPUT TYPES  (what our map produces)
# ---------------------------------------------------------------------------


@dataclass
class KeySignature:
    tonic: str
    mode: str


@dataclass
class EnrichedSegment:
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


@dataclass
class ModelRef:
    name: str
    version: str


@dataclass
class Sources:
    beats: ModelRef
    chords: ModelRef
    structure: ModelRef


@dataclass
class Meta:
    audio_hash: str
    generated_at: str
    map_version: str


@dataclass
class MusicMap:
    path: str
    bpm: int
    time_signature: TimeSignature
    duration: float
    beats: list[BeatTime]
    bars: list[BeatTime]
    segments: list[EnrichedSegment]
    sources: Sources
    meta: Meta
    key: Optional[KeySignature] = None  # TODO: implement via music21
