#!/usr/bin/env python3
"""Drift check for the `music-theory` skill.

Mirrors skills/cutting/scripts/check_skill.py's role, adapted for a skill with
no code API of its own: checks internal links, that every SegmentName mention
matches recut's live literal, and that every recut-format chord example
(`root:quality`) in assets/chord-notation.md is actually in the live chord
vocabulary — catching a typo'd example the way the cutting skill's checker
catches a stale parameter name.

Run via tests/skills/test_music_theory_skill.py under `pytest tests/`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

ROOT = Path(__file__).resolve().parents[1]  # skills/music-theory/
REPO_ROOT = ROOT.parents[1]
REFERENCES = ROOT / "references"
ASSETS = ROOT / "assets"

MD_PATH_RE = re.compile(r"(?<![\w./-])(?:\.\.?/)?[A-Za-z0-9_./#-]+\.md(?:#[A-Za-z0-9_./#-]+)?")
SEGMENT_LIST_RE = re.compile(r"`((?:[a-z-]+ \| )+[a-z-]+)`")
CHORD_TOKEN_RE = re.compile(r"`([A-G][#b]?:[A-Za-z0-9()#b/*]+)`")


def check_broken_links() -> list[str]:
    errors = []
    for md_file in list(REFERENCES.glob("*.md")) + list(ASSETS.glob("*.md")):
        text = md_file.read_text()
        for match in MD_PATH_RE.findall(text):
            path_part = match.split("#")[0]
            candidates = [md_file.parent / path_part, ROOT / path_part, REPO_ROOT / path_part]
            if not any(c.resolve().exists() for c in candidates):
                errors.append(f"{md_file.relative_to(ROOT)}: broken link {match!r}")
    return errors


def check_segment_names() -> list[str]:
    """The skill states recut's full SegmentName set as one canonical
    backtick-wrapped, pipe-separated list (song-form-and-sections.md). Assert
    it still matches the live literal exactly, in order — this is the one
    place drift would actually matter; scanning every stray lowercase-hyphen
    backtick token elsewhere (e.g. `lead-sheet`) would just produce noise.
    """
    from recut.map.schema import SegmentName

    live = get_args(SegmentName)
    doc = REFERENCES / "song-form-and-sections.md"
    text = doc.read_text()

    match = SEGMENT_LIST_RE.search(text)
    if not match:
        return [f"{doc.relative_to(ROOT)}: no canonical SegmentName list found"]

    documented = tuple(match.group(1).split(" | "))
    if documented != live:
        return [
            f"{doc.relative_to(ROOT)}: documented SegmentName list {documented} "
            f"does not match live recut.map.schema.SegmentName {live}"
        ]
    return []


def check_chord_examples() -> list[str]:
    from recut.map.schema import is_valid_chord

    errors = []
    chord_doc = ASSETS / "chord-notation.md"
    for token in CHORD_TOKEN_RE.findall(chord_doc.read_text()):
        if token == "N":
            continue
        if not is_valid_chord(token):
            errors.append(f"{chord_doc.relative_to(ROOT)}: invalid chord example `{token}`")
    return errors


def run() -> list[str]:
    return check_broken_links() + check_segment_names() + check_chord_examples()


if __name__ == "__main__":
    import sys

    issues = run()
    for issue in issues:
        print(issue)
    sys.exit(1 if issues else 0)
