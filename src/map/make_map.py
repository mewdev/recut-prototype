"""
make_map.py — enrich raw analysis JSON into a music map

Input:  <stem>-raw.json   (beats, downbeats, segments, chords from analysis pipeline)
        <stem>.mp3         (audio, for loudness)
Output: <stem>-map.json   (enriched, LLM-ready)

Usage:
    python -m map.make_map temp/analysis/raw/track-raw.json mp3/track.mp3
"""

import json
from datetime import datetime
from pathlib import Path

import librosa
import numpy as np

from map.helpers import chords_in, downbeats_in, hash_file, loudness_rms_db, phrase_in
from map.schema import BeatTime, ChordEntry, EnrichedSegment, MusicMap, RawAnalysis, RawSegment


def build_segment(
    segment: RawSegment,
    index: int,
    all_downbeats: list[BeatTime],
    all_chords: list[ChordEntry],
    all_phrases: list[BeatTime],
    audio: np.ndarray,
    sample_rate: int,
) -> EnrichedSegment:
    seg_downbeats = downbeats_in(all_downbeats, segment["start"], segment["end"])
    seg_audio = audio[int(segment["start"] * sample_rate) : int(segment["end"] * sample_rate)]
    return {
        "index": index,
        "label": segment["label"],
        "start": segment["start"],
        "end": segment["end"],
        "duration": segment["end"] - segment["start"],
        "bars": len(seg_downbeats),
        "downbeats": seg_downbeats,
        "phrases": [p for p in all_phrases if segment["start"] <= p < segment["end"]],
        "chords": chords_in(all_chords, segment["start"], segment["end"]),
        "loudness_db": loudness_rms_db(seg_audio),
        "loudness_db_start": loudness_rms_db(seg_audio[: int(0.5 * sample_rate)]),
        "loudness_db_end": loudness_rms_db(seg_audio[-int(0.5 * sample_rate) :]),
    }


def run(chordmini_path: str, audio_path: str) -> MusicMap:
    data: RawAnalysis = json.loads(Path(chordmini_path).read_text())
    audio, sr = librosa.load(audio_path, sr=None)
    sr = int(sr)

    all_phrases = phrase_in(data["downbeats"])

    segments = [
        build_segment(segment, index, data["downbeats"], data["chords"], all_phrases, audio, sr)
        for index, segment in enumerate(data["segments"])
    ]

    return {
        "path": audio_path,
        "bpm": data["bpm"],
        "key": None,  # TODO: implement via music21
        "time_signature": data["time_signature"],
        "duration": len(audio) / sr,
        "beats": data["beats"],
        "bars": data["downbeats"],
        "segments": segments,
        "sources": {
            # TODO: add proper model versions
            "beats": {"name": "chordmini", "version": "1.0"},
            "chords": {"name": "chordmini", "version": "1.0"},
            "structure": {"name": "chordmini", "version": "1.0"},
        },
        "meta": {
            "audio_hash": hash_file(audio_path),
            "generated_at": datetime.utcnow().isoformat(),
            "map_version": "0.1",
        },
    }


if __name__ == "__main__":
    import sys

    chordmini_path = sys.argv[1]
    result = run(chordmini_path, sys.argv[2])
    out_path = chordmini_path.replace("-raw.json", "-map.json")
    Path(out_path).write_text(json.dumps(result, indent=2))
    print(f"Written to {out_path}")
