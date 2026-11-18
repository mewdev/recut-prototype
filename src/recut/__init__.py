import os

# librosa's numba functions cache next to site-packages; where that is read-only (agent
# sandboxes, shared envs) every import failed with "cannot cache function ...: no locator
# available". Cache in the user's cache dir instead, unless the caller chose one.
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "numba-recut"))
