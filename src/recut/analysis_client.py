"""Client for the Modal analysis pipeline (src/analysis/pipeline.py).

Needs a deployed `recut-analysis` app and a Modal token on this machine (`modal token new`).
"""

import json
import tempfile
import time
from pathlib import Path

from recut.map.schema import MusicMap

_APP = "recut-analysis"


def analyze_raw(audio_path: Path, log=print) -> dict:
    """Run beats + chords + structure + key on Modal in parallel → raw analysis dict."""
    from modal import Function  # lazy: only machines that analyze need Modal configured

    audio_bytes = audio_path.read_bytes()
    filename = audio_path.name
    log(f"Sending {filename} → Modal (beats + chords + structure + key)...")
    t0 = time.time()
    calls = {
        name: Function.from_name(_APP, f"run_{name}").spawn(audio_bytes, filename)
        for name in ("beats", "chords", "structure", "key")
    }
    beats = calls["beats"].get()
    log(f"  ✓ beats      bpm={beats['bpm']}  ({time.time() - t0:.0f}s)")
    chords = calls["chords"].get()
    log(f"  ✓ chords     {len(chords['chords'])} chords  ({time.time() - t0:.0f}s)")
    structure = calls["structure"].get()
    log(f"  ✓ structure  {len(structure['segments'])} segments  ({time.time() - t0:.0f}s)")
    key = calls["key"].get()
    log(f"  ✓ key        {key['key']}  ({time.time() - t0:.0f}s)")
    return {
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


def analyze_to_map(audio_path: Path) -> MusicMap:
    """Modal analysis + enrichment → MusicMap for one audio file."""
    from recut.map.make_map import run as make_map

    raw = analyze_raw(audio_path)
    with tempfile.TemporaryDirectory() as tmp:
        raw_path = Path(tmp) / f"{audio_path.stem}.json"
        raw_path.write_text(json.dumps(raw))
        return make_map(raw_path, audio_path)
