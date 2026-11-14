"""
enrich.py — add the M2 fields (pace, short-term loudness, key ranges) to EXISTING maps.

Needs only the audio and the map's own beat grid: no Modal, no re-analysis. The map is otherwise
unchanged (segments keep their boundaries; each gets a `pace` summary).
"""

import json
from pathlib import Path

import librosa

from recut.map.musicdata import enrich_map
from recut.map.schema import MusicMap


def has_music_data(m: MusicMap) -> bool:
    return m.pace is not None and m.loudness_short_term is not None and m.key_ranges is not None


def enrich_map_file(map_path: str | Path, audio_path: str | Path, force: bool = False) -> bool:
    """Rewrite `map_path` with the M2 fields. Returns False (file untouched) when it already has
    them all and `force` is off."""
    map_path = Path(map_path)
    m = MusicMap.model_validate_json(map_path.read_text())
    if has_music_data(m) and not force:
        return False
    audio, sr = librosa.load(audio_path, sr=None)
    m = enrich_map(m, audio, int(sr), force=force)
    tmp = map_path.with_suffix(map_path.suffix + ".tmp")
    tmp.write_text(json.dumps(m.model_dump(), indent=2))
    tmp.replace(map_path)
    return True
