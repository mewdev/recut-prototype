"""Where recut keeps its data (.appdata/): audio, maps, compositions, renders, tickets.

Resolved once, independent of the current directory:
1. `RECUT_HOME` env var, if set (the folder that contains/should contain the data)
2. the repo root, when recut runs from a source checkout (`pip install -e .`)
3. the current directory (installed as a plain package)
"""

import os
from pathlib import Path


def _home() -> Path:
    env = os.environ.get("RECUT_HOME")
    if env:
        return Path(env).expanduser().resolve()
    repo = Path(__file__).resolve().parents[2]
    if (repo / "pyproject.toml").exists() and (repo / "src" / "recut").is_dir():
        return repo
    return Path.cwd()


HOME = _home()
APPDATA = HOME / ".appdata"
AUDIO_DIR = APPDATA / "audio"
RAW_DIR = APPDATA / "maps" / "raw"
MAP_DIR = APPDATA / "maps" / "enriched"
COMPOSITIONS_DIR = APPDATA / "compositions"
RENDERS_DIR = APPDATA / "renders"
TICKETS_DIR = APPDATA / "tickets"
