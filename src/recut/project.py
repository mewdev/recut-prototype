from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from recut.map.helpers import hash_file
from recut.map.parser import parse_recut_map
from recut.map.schema import MusicMap
from recut.paths import AUDIO_DIR, MAP_DIR, RAW_DIR

SourceStatus = Literal["ready", "needs_map", "needs_analysis", "hash_mismatch"]


@dataclass
class Source:
    name: str
    audio_path: Path
    music_map: Optional[MusicMap]
    status: SourceStatus


AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".m4a"}


def load_project_sources() -> dict[str, Source]:
    sources = {}

    for audio_file in AUDIO_DIR.iterdir():
        if not (audio_file.is_file() and audio_file.suffix.lower() in AUDIO_EXTENSIONS):
            continue

        stem = audio_file.stem
        map_path = MAP_DIR / f"{stem}.json"

        if not map_path.exists():
            raw_path = RAW_DIR / f"{stem}.json"
            if not raw_path.exists():
                source = Source(
                    name=stem, audio_path=audio_file, music_map=None, status="needs_analysis"
                )
            else:
                source = Source(
                    name=stem, audio_path=audio_file, music_map=None, status="needs_map"
                )
        else:
            music_map = parse_recut_map(map_path)
            source = Source(name=stem, audio_path=audio_file, music_map=music_map, status="ready")
            if not verify_source_hash(source):
                source.status = "hash_mismatch"

        sources[stem] = source

    return sources


def verify_source_hash(source: Source) -> bool:

    if source.music_map is None:
        return False
    return hash_file(source.audio_path) == source.music_map.meta.audio_hash
