"""
make_map.py — enrich raw analysis JSON into a music map

Input:  .appdata/maps/raw/<stem>.json   (beats, downbeats, segments, chords from analysis pipeline)
        .appdata/audio/<stem>.mp3       (audio, for loudness)
Output: .appdata/maps/enriched/<stem>.json

Usage:
    python -m map.make_map temp/analysis/raw/track-raw.json mp3/track.mp3
"""


import json
from datetime import datetime
from pathlib import Path

import librosa
import numpy as np

from recut.map.helpers import chords_in, downbeats_in, hash_file, loudness_rms_db, phrase_in
from recut.map.schema import (
    BeatTime,
    ChordEntry,
    EnrichedSegment,
    Meta,
    ModelRef,
    MusicMap,
    RawAnalysis,
    RawSegment,
    Sources,
)


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
    return EnrichedSegment(
        index=index,
        segment_name=segment["label"],
        start=segment["start"],
        end=segment["end"],
        duration=segment["end"] - segment["start"],
        bars=len(seg_downbeats),
        downbeats=seg_downbeats,
        phrases=[p for p in all_phrases if segment["start"] <= p < segment["end"]],
        chords=chords_in(all_chords, segment["start"], segment["end"]),
        loudness_db=loudness_rms_db(seg_audio),
        loudness_db_start=loudness_rms_db(seg_audio[: int(0.5 * sample_rate)]),
        loudness_db_end=loudness_rms_db(seg_audio[-int(0.5 * sample_rate) :]),
    )


def run(raw_path: str | Path, audio_path: str | Path) -> MusicMap:
    data: RawAnalysis = json.loads(Path(raw_path).read_text())
    audio, sr = librosa.load(audio_path, sr=None)
    sr = int(sr)

    all_phrases = phrase_in(data["downbeats"])

    segments = [
        build_segment(segment, index, data["downbeats"], data["chords"], all_phrases, audio, sr)
        for index, segment in enumerate(data["segments"])
    ]

    return MusicMap(
        path=str(audio_path),
        bpm=data["bpm"],
        time_signature=data["time_signature"],
        duration=len(audio) / sr,
        beats=data["beats"],
        bars=data["downbeats"],
        segments=segments,
        sources=Sources(
            # TODO: pin Modal image to specific git commits and propagate versions here
            beats=ModelRef(name=data["_sources"]["beats"], version="unknown"),
            chords=ModelRef(name=data["_sources"]["chords"], version="unknown"),
            structure=ModelRef(name=data["_sources"]["structure"], version="unknown"),
        ),
        meta=Meta(
            audio_hash=hash_file(audio_path),
            generated_at=datetime.utcnow().isoformat(),
            map_version="0.1",
        ),
    )


if __name__ == "__main__":
    import sys

    raw_path = Path(sys.argv[1])
    audio_path = Path(sys.argv[2])
    result = run(raw_path, audio_path)
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else raw_path.parent.parent / "enriched" / f"{raw_path.stem}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.model_dump(), indent=2))
    print(f"Written to {out_path}")
