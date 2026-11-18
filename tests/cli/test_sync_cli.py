"""`recut sync` says what its status means, so nobody re-runs a sync that already did its job
(agents re-ran a "queued" sync with the sandbox off)."""

import re
import sys
from pathlib import Path

import pytest

from recut import sync
from recut.cli import SYNC_MEANING, main


def test_every_status_sync_returns_is_explained():
    src = Path(sync.__file__).read_text()
    returned = set(re.findall(r'"status": "([a-z-]+)"', src)) | {"committed", "clean"}
    assert returned <= set(SYNC_MEANING)


@pytest.mark.parametrize("status, words", [("queued", "Nothing to do"), ("push-failed", "NOT pushed"),
                                           ("pushed", "saved")])
def test_prints_the_meaning(status, words, monkeypatch, capsys):
    monkeypatch.setattr(sync, "sync", lambda *a, **kw: {"status": status})
    monkeypatch.setattr(sys, "argv", ["recut", "sync"])
    main()
    out = capsys.readouterr().out
    assert out.startswith(f"sync: {status} — ") and words in out
