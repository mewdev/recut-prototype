"""
make_map.py — enrich raw analysis JSON into a music map

Input:  .appdata/maps/raw/<stem>.json   (beats, downbeats, segments, chords from analysis pipeline)
        .appdata/audio/<stem>.mp3       (audio, for loudness)
Output: .appdata/maps/enriched/<stem>.json

Usage:
    python -m map.make_map temp/analysis/raw/track-raw.json mp3/track.mp3
"""

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import librosa
import numpy as np

from recut.map.helpers import (
    chords_in,
    downbeats_in,
    hash_file,
    loudness_rms_db,
    parse_key,
    phrase_in,
    snap_to_downbeat,
)
from recut.map.musicdata import enrich_map
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
from recut.map.tempo import bpm_disagrees, bpm_from_beats


def build_segment(
    segment: RawSegment,
    index: int,
    all_downbeats: list[BeatTime],
    all_chords: list[ChordEntry],
    all_phrases: list[BeatTime],
    audio: np.ndarray,
    sample_rate: int,
    is_last: bool = False,
    is_first: bool = False,
) -> EnrichedSegment:
    # the song's head (pickup / lead-in before the first downbeat) has no downbeat to snap to:
    # the first segment starts at 0.0 so no audio is lost. Its bars still count real downbeats.
    start = 0.0 if is_first else snap_to_downbeat(all_downbeats, segment["start"])
    # the song's tail (fade-out, silence) has no downbeat to snap to — last segment runs to end of audio
    end = len(audio) / sample_rate if is_last else snap_to_downbeat(all_downbeats, segment["end"])
    seg_downbeats = downbeats_in(all_downbeats, start, end)
    seg_audio = audio[int(start * sample_rate) : int(end * sample_rate)]
    return EnrichedSegment(
        index=index,
        segment_name=segment["label"],
        start=start,
        end=end,
        duration=end - start,
        bars=len(seg_downbeats),
        downbeats=seg_downbeats,
        phrases=[p for p in all_phrases if start <= p < end],
        chords=chords_in(all_chords, start, end),
        loudness_db=loudness_rms_db(seg_audio),
        loudness_db_start=loudness_rms_db(seg_audio[: int(0.5 * sample_rate)]),
        loudness_db_end=loudness_rms_db(seg_audio[-int(0.5 * sample_rate) :]),
    )


def run(raw_path: str | Path, audio_path: str | Path) -> MusicMap:
    data: RawAnalysis = json.loads(Path(raw_path).read_text())
    audio, sr = librosa.load(audio_path, sr=None)
    sr = int(sr)

    all_phrases = phrase_in(data["downbeats"])

    n_raw = len(data["segments"])
    segments = [
        build_segment(
            segment, index, data["downbeats"], data["chords"], all_phrases, audio, sr,
            is_last=index == n_raw - 1, is_first=index == 0,
        )
        for index, segment in enumerate(data["segments"])
    ]
    # two raw boundaries snapping to the same downbeat leave a zero-length segment: drop it
    # (no audio is lost) and renumber
    kept = [seg for seg in segments if seg.duration > 0]
    if len(kept) < len(segments):
        dropped = [s.segment_name for s in segments if s.duration <= 0]
        print(f"make_map: dropped zero-length segments: {dropped}")
        segments = [seg.model_copy(update={"index": i}) for i, seg in enumerate(kept)]

    # tempo: the beat grid is what cuts land on; the estimator can be half/double time
    raw_bpm = float(data["bpm"])
    grid_bpm = bpm_from_beats(data["beats"])
    bpm, bpm_raw = raw_bpm, None
    if grid_bpm is not None:
        bpm = round(grid_bpm, 2)
        if bpm_disagrees(raw_bpm, grid_bpm):
            bpm_raw = raw_bpm
            warnings.warn(
                f"tempo estimate {raw_bpm:.2f} bpm disagrees with the beat grid "
                f"({grid_bpm:.2f} bpm); using the grid",
                stacklevel=2,
            )

    raw_key = data.get("key")
    sources = data["_sources"]
    raw_key_source = sources.get("key")

    music_map = MusicMap(
        path=str(audio_path),
        bpm=bpm,
        bpm_raw=bpm_raw,
        beats_per_bar=data["beats_per_bar"],
        duration=len(audio) / sr,
        beats=data["beats"],
        bars=data["downbeats"],
        segments=segments,
        key=parse_key(raw_key) if raw_key else None,
        sources=Sources(
            # TODO: pin Modal image to specific git commits and propagate versions here
            beats=ModelRef(name=sources["beats"], version="unknown"),
            chords=ModelRef(name=sources["chords"], version="unknown"),
            structure=ModelRef(name=sources["structure"], version="unknown"),
            key=ModelRef(name=raw_key_source, version="unknown") if raw_key_source else None,
        ),
        meta=Meta(
            audio_hash=hash_file(audio_path),
            generated_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            map_version="0.1",
        ),
    )
    # M2: pace, short-term loudness, key ranges (CPU; ~5 s for a 3-minute track)
    return enrich_map(music_map, audio, sr)


if __name__ == "__main__":
    import sys

    raw_path = Path(sys.argv[1])
    audio_path = Path(sys.argv[2])
    result = run(raw_path, audio_path)
    out_path = (
        Path(sys.argv[3])
        if len(sys.argv) > 3
        else raw_path.parent.parent / "enriched" / f"{raw_path.stem}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.model_dump(), indent=2))
    print(f"Written to {out_path}")
