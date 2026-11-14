"""Save ticket data to the data repo (mewdev/recut-data): commit + push, automatically.

Every ticket action (new, work, iterate, render, review, client decision) calls
`request_sync()`. When the tickets folder lives in a git repo (the sibling `recut-data`
checkout, see recut.paths), that commits everything except audio and pushes it, so the
data is safe off-machine and readable from any session: Claude Code CLI on the Mac or a
cloud session. Without a data repo it does nothing.

- Off switch: `RECUT_AUTOSYNC=0`.
- Audio never goes to git (size, client copyright): the data repo's `.gitignore` excludes it.
- Safe with several processes (server, CLI, Stop hook): one lock file per repo; a sync
  that finds the lock taken leaves a "pending" mark and the lock holder syncs again.
- Never raises into the caller: a failed push is reported and retried by the next sync.
"""

import fcntl
import os
import socket
import subprocess
import threading
from pathlib import Path
from typing import Optional

from recut.paths import TICKETS_DIR

GITIGNORE = """\
# recut-data: audio never goes to git (size + client copyright). Written by recut.sync.
*.wav
*.mp3
*.flac
*.aif
*.aiff
*.m4a
*.ogg
*.tmp
*.tmp.*
.current_session
"""


def enabled() -> bool:
    return os.environ.get("RECUT_AUTOSYNC", "1").strip().lower() not in ("0", "false", "off", "no")


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=check, timeout=120)


def repo_root(tickets_dir: Path = TICKETS_DIR) -> Optional[Path]:
    """The git repo that holds the tickets folder, if it's a data repo (not the code repo)."""
    probe = tickets_dir if tickets_dir.exists() else tickets_dir.parent
    if not probe.exists():
        return None
    r = _git(probe, "rev-parse", "--show-toplevel", check=False)
    if r.returncode != 0:
        return None
    root = Path(r.stdout.strip())
    if (root / "pyproject.toml").exists() and (root / "src" / "recut").is_dir():
        return None  # the code repo: tickets in .appdata/ are git-ignored there, nothing to sync
    return root


def _has_remote(repo: Path) -> bool:
    return bool(_git(repo, "remote", check=False).stdout.strip())


def _branch(repo: Path) -> str:
    r = _git(repo, "symbolic-ref", "--short", "HEAD", check=False)
    return r.stdout.strip() or "main"


def sync(tickets_dir: Path = TICKETS_DIR, message: Optional[str] = None, push: bool = True) -> dict:
    """Commit all ticket data (no audio) and push. Returns {"status": ..., ...}."""
    repo = repo_root(tickets_dir)
    if repo is None:
        return {"status": "no-data-repo"}
    lock_path = repo / ".git" / "recut-sync.lock"
    pending = repo / ".git" / "recut-sync.pending"
    with open(lock_path, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pending.touch()  # the running sync will go round once more
            return {"status": "queued"}
        try:
            result = {"status": "clean"}
            while True:
                pending.unlink(missing_ok=True)
                result = _sync_once(repo, message, push)
                if not pending.exists():
                    return result
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _sync_once(repo: Path, message: Optional[str], push: bool) -> dict:
    gi = repo / ".gitignore"
    if not gi.exists() or "recut.sync" not in gi.read_text():
        gi.write_text(GITIGNORE + ("\n" + gi.read_text() if gi.exists() else ""))
    _git(repo, "add", "-A")
    committed = False
    if _git(repo, "diff", "--cached", "--quiet", check=False).returncode != 0:
        n = len(_git(repo, "diff", "--cached", "--name-only").stdout.split())
        msg = message or f"sync: {n} file(s) from {socket.gethostname()}"
        env_args = []
        if not _git(repo, "config", "user.email", check=False).stdout.strip():
            env_args = ["-c", "user.name=recut", "-c", "user.email=recut@localhost"]
        _git(repo, *env_args, "commit", "-q", "-m", msg)
        committed = True
    if not push or not _has_remote(repo):
        return {"status": "committed" if committed else "clean", "pushed": False}
    branch = _branch(repo)
    pull = _git(repo, "pull", "-q", "--rebase", "--autostash", "origin", branch, check=False)
    if pull.returncode != 0 and "couldn't find remote ref" not in pull.stderr:
        _git(repo, "rebase", "--abort", check=False)
        return {"status": "push-failed", "error": pull.stderr.strip()[-400:], "committed": committed}
    p = _git(repo, "push", "-q", "-u", "origin", branch, check=False)
    if p.returncode != 0:
        return {"status": "push-failed", "error": p.stderr.strip()[-400:], "committed": committed}
    return {"status": "pushed", "committed": committed}


def request_sync(reason: str = "", tickets_dir: Path = TICKETS_DIR, wait: bool = False) -> Optional[dict]:
    """Called after every ticket write. `wait=True` for short-lived CLI commands (a background
    thread would die with the process); servers use a background thread. Concurrent requests
    coalesce through the repo lock + pending mark in `sync()`."""
    if not enabled():
        return None
    message = f"sync: {reason}" if reason else None
    if wait:
        return _safe(tickets_dir, message)
    threading.Thread(target=_safe, args=(tickets_dir, message), daemon=True).start()
    return None


def _safe(tickets_dir: Path, message: Optional[str]) -> dict:
    try:
        return sync(tickets_dir, message)
    except Exception as e:  # never break a ticket action because git had a bad day
        return {"status": "error", "error": str(e)[:400]}
