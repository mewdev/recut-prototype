"""
parser.py — parse map formats into MusicMap

Public parsers:
  parse_recut_map(path)      — our enriched JSON format
  parse_recut_map_dict(src)  — same, from already-loaded dict
  parse_muf_map(path)        — NOT YET IMPLEMENTED

MusicMap helpers (used by validator + compositor):
  get_segment(music_map, segment_name, index) -> EnrichedSegment
  bars_to_seconds(music_map, bars) -> float
  beats_to_seconds(music_map, beats) -> float
  first_segment(music_map) -> EnrichedSegment
  last_segment(music_map) -> EnrichedSegment
"""

from pathlib import Path

from recut.map.schema import EnrichedSegment, MusicMap, SegmentName

# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------


def parse_recut_map(map_path: str) -> MusicMap:
    """Parse our enriched JSON map format. Pydantic validates structure automatically."""
    return MusicMap.model_validate_json(Path(map_path).read_text())


def parse_recut_map_dict(src: dict) -> MusicMap:
    """Parse our map format from an already-loaded dict."""
    return MusicMap.model_validate(src)


def parse_muf_map(muf_path: str) -> MusicMap:
    raise NotImplementedError("MUF parser not yet implemented")


def parse_muf_map_dict(src: dict) -> MusicMap:
    raise NotImplementedError("MUF parser not yet implemented")


def get_segment(music_map: MusicMap, segment_name: SegmentName, index: int = 1) -> EnrichedSegment:
    segments = [segment for segment in music_map.segments if segment.segment_name == segment_name]

    if len(segments) < index:
        raise ValueError(f"No {segment_name!r} segment at index {index}")

    return segments[index - 1]


def get_bpm(music_map: MusicMap) -> float:
    return music_map.bpm


def bars_to_seconds(music_map: MusicMap, bars: float) -> float:
    beats_per_bar = int(music_map.time_signature.split("/")[0])
    return bars * beats_per_bar * (60 / music_map.bpm)


def beats_to_seconds(music_map: MusicMap, beats: float) -> float:
    return beats * (60 / music_map.bpm)


def first_segment(music_map: MusicMap) -> EnrichedSegment:
    segments = [segment for segment in music_map.segments if segment.segment_name != "silence"]
    return segments[0]


def last_segment(music_map: MusicMap) -> EnrichedSegment:
    segments = [segment for segment in music_map.segments if segment.segment_name != "silence"]
    return segments[-1] if segments else music_map.segments[-1]
