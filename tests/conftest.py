import os
import tempfile

# Tests never touch the real tickets folder or the data repo (set before recut is imported).
os.environ["RECUT_TICKETS_DIR"] = tempfile.mkdtemp(prefix="recut-test-tickets-")
os.environ["RECUT_AUTOSYNC"] = "0"

import pytest

from recut import tickets


@pytest.fixture(scope="session")
def demo(tmp_path_factory):
    """Demo ticket (examples/summer-party, 2 rendered iterations) in a temp tickets root."""
    root = tmp_path_factory.mktemp("tickets")
    tid = tickets.create_demo_ticket(root=root)
    return root, tid
