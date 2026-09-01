"""
helpers.py — pure helper functions for map enrichment
"""

import bisect
import hashlib
from pathlib import Path

import numpy as np

from recut.map.schema import BeatTime, ChordEntry, KeySignature


# TODO: understand chunked hashing algo better
def hash_file(filepath: str | Path, block_size: int = 65536) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            sha256.update(block)
    return sha256.hexdigest()


def phrase_in(downbeats: list[BeatTime]) -> list[BeatTime]:
    if not downbeats:
        raise ValueError("Cannot create phrases: downbeat list is empty")
    # TODO: adjust 2-bar phrasing if results are not satisfactory
    return [downbeats[i] for i in range(0, len(downbeats), 2)]


# TODO: min_overlap fixes chord bleeding into wrong segments — chords and segments
# come from different models, so timestamps can be slightly mismatched
def chords_in(
    chords: list[ChordEntry], start: float, end: float, min_overlap: float = 0.2
) -> list[ChordEntry]:
    return [
        chord
        for chord in chords
        if min(chord["end"], end) - max(chord["start"], start) >= min_overlap
    ]


def downbeats_in(downbeats: list[BeatTime], start: float, end: float) -> list[BeatTime]:
    # Half-open [start, end): the shared boundary downbeat belongs to the
    # next segment. Exception: the song's last downbeat has no next segment
    # to claim it, so it must stay in whichever segment ends there.
    is_song_end = bool(downbeats) and end >= downbeats[-1]
    return [d for d in downbeats if start <= d < end or (is_song_end and d == end)]


# Segment boundaries come from a structure model (SongFormer) independent of
# the beat tracker, so raw start/end can land tens to hundreds of ms off the
# nearest bar line. Segments are musically sections, which start on downbeats
# — so replace the structure model's fuzzy timestamp with the beat tracker's
# precise one, same approach as Apple MUF's shouldSnapToBars.
def snap_to_downbeat(downbeats: list[BeatTime], time: float) -> BeatTime:
    if not downbeats:
        raise ValueError("Cannot snap: downbeat list is empty")
    index = bisect.bisect_left(downbeats, time)
    if index == 0:
        return downbeats[0]
    if index == len(downbeats):
        return downbeats[-1]
    before, after = downbeats[index - 1], downbeats[index]
    return before if time - before < after - time else after


def parse_key(label: str) -> KeySignature:
    # "F# minor" -> KeySignature(tonic="F#", mode="minor") — matches madmom's
    # key_prediction_to_label() output format (KEY_LABELS in madmom.features.key)
    tonic, mode = label.rsplit(" ", 1)
    return KeySignature(tonic=tonic, mode=mode)


def loudness_rms_db(audio: np.ndarray) -> float:
    rms = np.sqrt(np.mean(audio**2))
    rms = max(rms, 1e-10)
    return 20 * np.log10(rms)
