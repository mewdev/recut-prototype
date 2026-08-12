"""
helpers.py — pure helper functions for map enrichment
"""

import hashlib

import numpy as np

from map.schema import BeatTime, ChordEntry


# TODO: understand chunked hashing algo better
def hash_file(filepath: str, block_size: int = 65536) -> str:
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
    return [d for d in downbeats if start <= d <= end]


def loudness_rms_db(audio: np.ndarray) -> float:
    rms = np.sqrt(np.mean(audio**2))
    rms = max(rms, 1e-10)
    return 20 * np.log10(rms)
