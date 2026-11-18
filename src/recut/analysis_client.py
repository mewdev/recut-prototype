"""Client for the Modal analysis pipeline (src/analysis/pipeline.py).

Needs a deployed `recut-analysis` app and a Modal token on this machine (`modal token new`).
"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from recut.map.schema import MusicMap

_APP = "recut-analysis"


def keep_stems() -> bool:
    """Keep the separated stem audio (~150 MB per track as FLAC)? Off by default: the map only
    needs the activity curves, and mashups will use a better separator (STATUS M7). Turn on
    with `RECUT_KEEP_STEMS=1` or the `--keep-stems` CLI flag."""
    return os.environ.get("RECUT_KEEP_STEMS", "").strip().lower() in ("1", "true", "yes", "on")


def _spawn_stems(audio_bytes: bytes, filename: str, log, return_stems: bool = False):
    """Start stem separation; None (and a warning) if it cannot even be started. Modal sends
    the stem audio back only with `return_stems`; the activity curves always come back."""
    from modal import Function

    try:
        return Function.from_name(_APP, "run_stems").spawn(audio_bytes, filename,
                                                           return_stems=return_stems)
    except Exception as e:  # noqa: BLE001  stems are optional (e.g. app deployed before M1)
        log(f"  ! stems unavailable, no instrument activity: {e}\n"
            f"    fix: `modal deploy src/analysis/pipeline.py` (app predates run_stems), then "
            f"`recut ticket enrich <id> --force` adds the activity curves to the existing maps")
        return None


def _collect_stems(call, stems_dir: Optional[Path], log) -> Optional[dict]:
    """Wait for run_stems. Saves returned FLACs to `stems_dir` (when given) and returns
    {"hop_s", "curves"}; on any failure logs a warning and returns None."""
    if call is None:
        return None
    try:
        res = call.get()
        if stems_dir is not None and res.get("stems"):
            stems_dir.mkdir(parents=True, exist_ok=True)
            for name, data in res["stems"].items():
                (stems_dir / f"{name}.flac").write_bytes(data)
        return {"hop_s": res["hop_s"], "curves": res["activity"]}
    except Exception as e:  # noqa: BLE001
        log(f"  ! stem separation failed, continuing without instrument activity: {e}")
        return None


def fetch_activity(audio_path: Path, stems_dir: Optional[Path] = None, log=print) -> Optional[dict]:
    """Modal only for stems: {"hop_s", "curves"} for one track. The stem FLACs are saved to
    `stems_dir` only when `keep_stems()` is on."""
    log(f"Sending {audio_path.name} → Modal (stems)...")
    call = _spawn_stems(audio_path.read_bytes(), audio_path.name, log,
                        return_stems=stems_dir is not None and keep_stems())
    return _collect_stems(call, stems_dir, log)


def analyze_raw(audio_path: Path, log=print, stems_dir: Optional[Path] = None) -> dict:
    """Run beats + chords + structure + key (+ stems, optional) on Modal in parallel → raw
    analysis dict. With `stems_dir` and `keep_stems()` on, the four stem FLACs are saved there
    (otherwise only the curves come back from Modal); the raw dict only
    carries the activity curves (`_activity`), never audio."""
    from modal import Function  # lazy: only machines that analyze need Modal configured

    audio_bytes = audio_path.read_bytes()
    filename = audio_path.name
    log(f"Sending {filename} → Modal (beats + chords + structure + key + stems)...")
    t0 = time.time()
    calls = {
        name: Function.from_name(_APP, f"run_{name}").spawn(audio_bytes, filename)
        for name in ("beats", "chords", "structure", "key")
    }
    stems_call = _spawn_stems(audio_bytes, filename, log,
                              return_stems=stems_dir is not None and keep_stems())
    beats = calls["beats"].get()
    log(f"  ✓ beats      bpm={beats['bpm']}  ({time.time() - t0:.0f}s)")
    chords = calls["chords"].get()
    log(f"  ✓ chords     {len(chords['chords'])} chords  ({time.time() - t0:.0f}s)")
    structure = calls["structure"].get()
    log(f"  ✓ structure  {len(structure['segments'])} segments  ({time.time() - t0:.0f}s)")
    key = calls["key"].get()
    log(f"  ✓ key        {key['key']}  ({time.time() - t0:.0f}s)")
    activity = _collect_stems(stems_call, stems_dir, log)
    if activity:
        log(f"  ✓ stems      {len(activity['curves'])} curves  ({time.time() - t0:.0f}s)")
    raw = {
        "path": filename,
        "bpm": beats["bpm"],
        "beats_per_bar": beats["beats_per_bar"],
        "beats": beats["beats"],
        "downbeats": beats["downbeats"],
        "segments": structure["segments"],
        "chords": chords["chords"],
        "key": key["key"],
        "_sources": {
            "beats": "madmom",
            "chords": "chord-cnn-lstm (full)",
            "structure": "songformer",
            "key": "essentia-key-extractor",
        },
    }
    if activity:
        raw["_activity"] = activity
        raw["_sources"]["instrument_activity"] = "demucs-htdemucs"
    return raw


def analyze_to_map(audio_path: Path, stems_dir: Optional[Path] = None) -> MusicMap:
    """Modal analysis + enrichment → MusicMap for one audio file."""
    from recut.map.make_map import run as make_map

    raw = analyze_raw(audio_path, stems_dir=stems_dir)
    with tempfile.TemporaryDirectory() as tmp:
        raw_path = Path(tmp) / f"{audio_path.stem}.json"
        raw_path.write_text(json.dumps(raw))
        return make_map(raw_path, audio_path)
