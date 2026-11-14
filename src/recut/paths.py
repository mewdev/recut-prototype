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


def resolve_tickets_dir(home: Path, env: dict) -> Path:
    """Tickets live in the data repo when there is one (docs/DATA.md):
    1. `RECUT_TICKETS_DIR` env var
    2. `<sibling recut-data checkout>/tickets`: a `recut-data` git repo next to this repo
       (~/Documents/dev/recut-data on the operator's Mac, /home/user/recut-data in cloud
       sessions), so every machine saves to the same place without configuration
    3. `<home>/.appdata/tickets` (no data repo: local only)
    """
    if env.get("RECUT_TICKETS_DIR"):
        return Path(env["RECUT_TICKETS_DIR"]).expanduser().resolve()
    sibling = home.parent / "recut-data"
    if (sibling / ".git").exists():
        return sibling / "tickets"
    return home / ".appdata" / "tickets"


HOME = _home()
APPDATA = HOME / ".appdata"
AUDIO_DIR = APPDATA / "audio"
RAW_DIR = APPDATA / "maps" / "raw"
MAP_DIR = APPDATA / "maps" / "enriched"
COMPOSITIONS_DIR = APPDATA / "compositions"
RENDERS_DIR = APPDATA / "renders"
TICKETS_DIR = resolve_tickets_dir(HOME, dict(os.environ))
