#!/usr/bin/env python3
"""Drift check for the `cutting` skill: doc signatures vs live src/recut code.

Compares docs against real importable signatures instead of regexes over prose —
this is the direct fix for the failure mode that made archive/skills/cutting go
stale (the API moved, the docs didn't).

Run via tests/skills/test_cutting_skill.py under `pytest tests/`.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]  # skills/cutting/
REPO_ROOT = ROOT.parents[1]
REFERENCES = ROOT / "references"

MD_PATH_RE = re.compile(r"(?<![\w./-])(?:\.\.?/)?[A-Za-z0-9_./#-]+\.md(?:#[A-Za-z0-9_./#-]+)?")
COMMENT_RE = re.compile(r"#[^\n]*")


def _live_signatures() -> dict[str, Any]:
    from recut.compositor import compose
    from recut.compositor.effects import Delay, Fade, FilterSweep, Reverb
    from recut.compositor.nodes import Clip, XFade
    from recut.map.parser import (
        bars_to_seconds,
        beats_to_seconds,
        first_segment,
        get_bpm,
        get_segment,
        last_segment,
    )
    from recut.primitives.chain import chain
    from recut.primitives.cut import cut
    from recut.primitives.delay import delay
    from recut.primitives.fade import fade
    from recut.primitives.filter_sweep import filter_sweep
    from recut.primitives.reverb import reverb
    from recut.primitives.xfade import xfade
    from recut.validator import validate

    return {
        "cut": cut,
        "fade": fade,
        "filter_sweep": filter_sweep,
        "reverb": reverb,
        "delay": delay,
        "xfade": xfade,
        "chain": chain,
        "Clip": Clip,
        "XFade": XFade,
        "Fade": Fade,
        "Reverb": Reverb,
        "Delay": Delay,
        "FilterSweep": FilterSweep,
        "compose": compose,
        "validate": validate,
        "get_segment": get_segment,
        "get_bpm": get_bpm,
        "bars_to_seconds": bars_to_seconds,
        "beats_to_seconds": beats_to_seconds,
        "first_segment": first_segment,
        "last_segment": last_segment,
    }


def _param_names(obj: Any) -> set[str]:
    return {p for p in inspect.signature(obj).parameters if p != "self"}


def _split_top_level(inner: str) -> list[str]:
    args: list[str] = []
    depth = 0
    buf = ""
    for ch in inner:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            args.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        args.append(buf)
    return args


def _extract_calls(text: str, name: str) -> list[list[str]]:
    """Find every `name(...)` in text (balanced parens); return each call's arg list."""
    calls = []
    for m in re.finditer(rf"\b{re.escape(name)}\(", text):
        depth = 1
        i = m.end()
        while i < len(text) and depth > 0:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        calls.append(_split_top_level(text[m.end() : i - 1]))
    return calls


def check_signature_drift() -> list[str]:
    errors = []
    api_ref_path = REFERENCES / "api-reference.md"
    text = COMMENT_RE.sub("", api_ref_path.read_text())

    for name, obj in _live_signatures().items():
        expected = _param_names(obj)
        calls = _extract_calls(text, name)
        if not calls:
            errors.append(f"api-reference.md: no documented call found for `{name}`")
            continue

        # A name can appear in several places (canonical signature + short usage
        # examples) — pass if ANY one of them documents the full param set exactly.
        documented_sets = []
        for call in calls:
            documented = set()
            for arg in call:
                token = re.match(r"[A-Za-z_][A-Za-z0-9_]*", arg.strip().lstrip("*"))
                if token:
                    documented.add(token.group())
            documented_sets.append(documented)

        if expected in documented_sets:
            continue

        # No exact match — report against the closest candidate for a useful message.
        closest = max(documented_sets, key=lambda d: len(d & expected))
        missing = expected - closest
        extra = closest - expected
        if missing:
            errors.append(f"api-reference.md: `{name}` missing documented params {sorted(missing)}")
        if extra:
            errors.append(f"api-reference.md: `{name}` documents unknown params {sorted(extra)}")

    return errors


def check_broken_links() -> list[str]:
    errors = []
    for md_file in REFERENCES.glob("*.md"):
        text = md_file.read_text()
        for match in MD_PATH_RE.findall(text):
            path_part = match.split("#")[0]
            candidates = [md_file.parent / path_part, ROOT / path_part, REPO_ROOT / path_part]
            if not any(c.resolve().exists() for c in candidates):
                errors.append(f"{md_file.relative_to(ROOT)}: broken link {match!r}")
    return errors


def check_segment_names() -> list[str]:
    from typing import get_args

    from recut.map.schema import SegmentName

    valid = set(get_args(SegmentName))

    map_doc = REFERENCES / "map-interpretation.md"
    text = map_doc.read_text()
    start = text.index("## Segment label guide")
    section = text[start:].split("## What")[0]

    used = set(re.findall(r"`([a-z-]+)`", section))
    unknown = used - valid
    return [f"map-interpretation.md: unknown segment label `{u}`" for u in sorted(unknown)]


def run() -> list[str]:
    return check_signature_drift() + check_broken_links() + check_segment_names()


if __name__ == "__main__":
    import sys

    issues = run()
    for issue in issues:
        print(issue)
    sys.exit(1 if issues else 0)
