"""Importing recut works where site-packages is read-only: numba caches in the user's cache dir."""

import os
import subprocess
import sys


def test_numba_cache_dir_defaults_to_user_cache(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "NUMBA_CACHE_DIR"}
    env["XDG_CACHE_HOME"] = str(tmp_path)
    out = subprocess.run([sys.executable, "-c", "import os, recut; print(os.environ['NUMBA_CACHE_DIR'])"],
                         env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert out == str(tmp_path / "numba-recut")


def test_caller_choice_wins(tmp_path):
    env = {**os.environ, "NUMBA_CACHE_DIR": str(tmp_path / "mine")}
    out = subprocess.run([sys.executable, "-c", "import os, recut; print(os.environ['NUMBA_CACHE_DIR'])"],
                         env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert out == str(tmp_path / "mine")
