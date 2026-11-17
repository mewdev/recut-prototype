"""
enrich.py — add the M2 fields (pace, short-term loudness, key ranges) and, optionally, the M1
instrument activity to EXISTING maps.

M2 needs only the audio and the map's own beat grid: no Modal, no re-analysis. The map is
otherwise unchanged (segments keep their boundaries; each gets `pace`, `drum_activity` and
`vocal_activity` summaries).

M1 (`stems_dir` given): saved stems (`<stems_dir>/<stem>.flac`) are reused, so no Modal;
without them Modal runs stem separation only (`analysis_client.fetch_activity`, which also saves
the FLACs there). If that fails the map is still written with the M2 fields.
"""

import json
from pathlib import Path
from typing import Callable, Optional

import librosa

from recut.map.activity import apply_activity, curves_from_stems_dir, has_activity
from recut.map.musicdata import enrich_map
from recut.map.schema import MusicMap


def has_music_data(m: MusicMap) -> bool:
    return m.pace is not None and m.loudness_short_term is not None and m.key_ranges is not None


def _default_fetch(audio_path: Path, stems_dir: Path) -> Optional[dict]:
    from recut.analysis_client import fetch_activity

    return fetch_activity(audio_path, stems_dir)


def get_activity_curves(audio_path: Path, stems_dir: Path,
                        fetch: Optional[Callable[[Path, Path], Optional[dict]]] = None,
                        log=print) -> Optional[tuple[dict, float]]:
    """(curves, hop_s) from saved stems, else from Modal (`fetch(audio, stems_dir)` →
    {"hop_s", "curves"}); None when neither works (a warning is logged)."""
    from recut.map.activity import HOP_S

    try:
        curves = curves_from_stems_dir(stems_dir)
    except Exception as e:  # noqa: BLE001  unreadable stems: fall back to Modal
        log(f"  ! could not read saved stems in {stems_dir}: {e}")
        curves = None
    if curves:
        return curves, HOP_S
    try:
        got = (fetch or _default_fetch)(audio_path, stems_dir)
    except Exception as e:  # noqa: BLE001
        log(f"  ! stem separation failed, no instrument activity: {e}")
        return None
    return (got["curves"], float(got["hop_s"])) if got else None


def enrich_map_file(map_path: str | Path, audio_path: str | Path, force: bool = False,
                    stems_dir: Optional[str | Path] = None,
                    fetch_stems: Optional[Callable[[Path, Path], Optional[dict]]] = None) -> bool:
    """Rewrite `map_path` with the missing fields. Returns False (file untouched) when nothing
    is missing and `force` is off. `stems_dir` turns on instrument activity (see module doc)."""
    map_path, audio_path = Path(map_path), Path(audio_path)
    m = MusicMap.model_validate_json(map_path.read_text())
    need_m2 = not has_music_data(m)
    need_activity = stems_dir is not None and not has_activity(m)
    if not (need_m2 or need_activity or force):
        return False
    changed = need_m2 or force
    if need_m2 or force:
        audio, sr = librosa.load(audio_path, sr=None)
        m = enrich_map(m, audio, int(sr), force=force)
    if stems_dir is not None and (need_activity or force):
        got = get_activity_curves(audio_path, Path(stems_dir), fetch_stems)
        if got:
            m = apply_activity(m, got[0], got[1])
            changed = True
    if not changed:  # only activity was missing and it could not be had: leave the file alone
        return False
    tmp = map_path.with_suffix(map_path.suffix + ".tmp")
    tmp.write_text(json.dumps(m.model_dump(), indent=2))
    tmp.replace(map_path)
    return True
