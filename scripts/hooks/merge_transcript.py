"""Merge one Claude Code transcript into a ticket session's transcript.jsonl (stdlib only).

Usage: python3 merge_transcript.py <claude transcript> <ticket session>/transcript.jsonl

Several Claude sessions can work the same ticket session (e.g. the operator resumes the
ticket later in a new Claude session). A plain copy let each Stop overwrite the others, so
transcript.jsonl is the concatenation of every session's transcript, and a Stop replaces
only the block(s) of the session(s) its transcript contains; everything else is kept, in
order. A line belongs to the session in its "sessionId"; lines without one (file-history
snapshots) belong to the next line that has one (the last block, at the end of the file).
The destination is replaced atomically (written to .tmp, then renamed).
"""

import json
import os
import sys


def _owners(lines: list[str]) -> list:
    out, pending = [], 0
    for line in lines:
        try:
            sid = json.loads(line).get("sessionId")
        except (ValueError, AttributeError):
            sid = None
        if sid is None:
            out.append(None)
            pending += 1
            continue
        out[len(out) - pending:] = [sid] * pending  # unowned lines join the next session
        out.append(sid)
        pending = 0
    if pending and len(out) > pending:  # trailing unowned lines join the last session
        out[len(out) - pending:] = [out[len(out) - pending - 1]] * pending
    return out


def _blocks(lines: list[str]) -> list[tuple]:
    blocks: list[tuple] = []
    for line, owner in zip(lines, _owners(lines)):
        if blocks and blocks[-1][0] == owner:
            blocks[-1][1].append(line)
        else:
            blocks.append((owner, [line]))
    return blocks


def _tag(line: str, owner, has_id: bool) -> str:
    """Write the owner into a line without a sessionId, so the merged file has no ambiguous
    lines (A's trailing snapshot next to B's leading one). The rest of the line is untouched."""
    if owner is None or has_id or not line.startswith("{"):
        return line
    rest = line[1:].lstrip()
    return '{"sessionId":' + json.dumps(owner) + ("" if rest.startswith("}") else ",") + rest


def merge(existing: str, new: str) -> str:
    new_lines = new.splitlines(keepends=True)
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"
    mine = {owner for owner, _ in _blocks(new_lines)}
    raw = [_owners([ln])[0] is not None for ln in new_lines]
    new_lines = [_tag(ln, o, h) for ln, o, h in zip(new_lines, _owners(new_lines), raw)]
    out, placed = [], False
    for owner, lines in _blocks(existing.splitlines(keepends=True)):
        if owner in mine:
            if not placed:  # this session's new copy goes where its old block was
                out += new_lines
                placed = True
            continue
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        out += lines
    if not placed:
        out += new_lines
    return "".join(out)


def main(src: str, dest: str) -> None:
    existing = open(dest, encoding="utf-8", errors="replace").read() if os.path.exists(dest) else ""
    new = open(src, encoding="utf-8", errors="replace").read()
    with open(dest + ".tmp", "w", encoding="utf-8") as f:
        f.write(merge(existing, new))
    os.replace(dest + ".tmp", dest)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
