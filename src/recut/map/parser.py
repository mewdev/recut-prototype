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

import warnings
from pathlib import Path

from recut.map.schema import EnrichedSegment, MusicMap, SegmentName
from recut.map.tempo import bpm_disagrees, bpm_from_beats

# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------


def parse_recut_map(map_path: str | Path) -> MusicMap:
    """Parse our enriched JSON map format. Pydantic validates structure automatically."""
    return _reconcile_bpm(MusicMap.model_validate_json(Path(map_path).read_text()))


def parse_recut_map_dict(src: dict) -> MusicMap:
    """Parse our map format from an already-loaded dict."""
    return _reconcile_bpm(MusicMap.model_validate(src))


def _reconcile_bpm(music_map: MusicMap) -> MusicMap:
    """Load-time guard: maps made before the beat-grid tempo fix can carry a half/double-time
    `bpm`, which makes every `bars` / `beats` unit wrong. Correct it from the map's own grid."""
    grid_bpm = bpm_from_beats(music_map.beats)
    if grid_bpm is not None and bpm_disagrees(music_map.bpm, grid_bpm):
        warnings.warn(
            f"map bpm {music_map.bpm:.2f} disagrees with its beat grid ({grid_bpm:.2f} bpm); "
            "using the grid (map predates the tempo fix; `recut map --force` persists it)",
            stacklevel=3,
        )
        music_map = music_map.model_copy(
            update={"bpm": round(grid_bpm, 2), "bpm_raw": music_map.bpm_raw or music_map.bpm}
        )
    return music_map


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
    return bars * music_map.beats_per_bar * (60 / music_map.bpm)


def beats_to_seconds(music_map: MusicMap, beats: float) -> float:
    return beats * (60 / music_map.bpm)


def first_segment(music_map: MusicMap) -> EnrichedSegment:
    segments = [segment for segment in music_map.segments if segment.segment_name != "silence"]
    return segments[0]


def last_segment(music_map: MusicMap) -> EnrichedSegment:
    segments = [segment for segment in music_map.segments if segment.segment_name != "silence"]
    return segments[-1] if segments else music_map.segments[-1]
