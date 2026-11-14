"""`recut ticket import-legacy`: a pre-refactor session export (recut-data/baseline/pre-refactor/<session>)
-> one normal ticket folder (PLAN §3.1), so `recut report` counts it as baseline.

Mapping (old `Clip`/`XFade` exports have no audio or maps, so nothing is rendered):
- ticket id `<YYYYMMDD>-legacy-<slug>-<hash4>`: date and slug from the export folder name,
  hash4 = first 4 hex of sha256(folder name). Same folder -> same id, so re-import is idempotent.
- request.json: text, target_duration_s, files (from the export's sources), created_at = session date.
  status: from the last client approval if any, else from the last review (ship -> in_review,
  otherwise needs_rework).
- sessions/1/meta.json: agent `legacy-pre-refactor` (THE baseline marker, read by `recut report`),
  model null (unknown), started_at = session date (00:00 UTC, the export has no time of day).
- sessions/1/intent.json: Intent fields only (unknown keys dropped).
- sessions/1/{transcript.jsonl,timeline.md,code_changes.md}: copied as-is.
- sessions/1/iterations/<k>/composition.json: copied as-is (old Clip/XFade format).
  plan.json is NOT written: `recut.legacy` needs the segment map to resolve clip bounds, and the
  export has no maps. The reason is recorded in sessions/1/import.json.
- sessions/1/iterations/<k>/review.json: Review fields only. `human_fix` is appended to the note as
  "human fix: ...". `client_approved` moves to client_feedback.jsonl.
- client_feedback.jsonl: one ClientFeedback per iteration whose review has `client_approved` set,
  channel manual, rating null, note null (only real client words go in notes: they are quoted in
  reports), at = export date. The import itself is recorded in sessions/1/import.json.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from recut import tickets
from recut.contracts import ClientFeedback, Intent, Request, Review, SessionMeta
from recut.paths import TICKETS_DIR

AGENT = "legacy-pre-refactor"
FEEDBACK_NOTE = None  # client notes are quoted in reports: never put tool-generated text there
_FOLDER = re.compile(r"^(\d{8})-(.+)$")


def ticket_id_for(export_dir: Path) -> str:
    """`YYYYMMDD-legacy-<slug>-<hash4>` from the export folder name (deterministic)."""
    name = export_dir.name
    m = _FOLDER.match(name)
    if not m:
        raise ValueError(f"export folder name must start with YYYYMMDD-: {name!r}")
    day, slug = m.group(1), m.group(2)
    slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")[:40] or "session"
    h = hashlib.sha256(name.encode()).hexdigest()[:4]
    return f"{day}-legacy-{slug}-{h}"


def _read(p: Path) -> dict:
    return json.loads(p.read_text())


def _iso(day_or_stamp: str) -> str:
    """A date (2026-11-14) -> midnight UTC; a full timestamp is kept as it is."""
    return day_or_stamp if "T" in day_or_stamp else f"{day_or_stamp}T00:00:00+00:00"


def _iteration_numbers(export_dir: Path) -> list[int]:
    d = export_dir / "iterations"
    return sorted(int(p.name) for p in d.iterdir() if p.name.isdigit()) if d.is_dir() else []


def import_export(export_dir: Path, root: Path = TICKETS_DIR, force: bool = False) -> str:
    """Import one pre-refactor export folder into `root`. Returns the ticket id.

    Raises FileExistsError when the ticket already exists (unless `force`, which replaces it).
    """
    export_dir = Path(export_dir).resolve()
    if not (export_dir / "request.json").exists():
        raise FileNotFoundError(f"not a session export (no request.json): {export_dir}")
    tid = ticket_id_for(export_dir)
    dest = root / tid
    if dest.exists():
        if not force:
            raise FileExistsError(f"ticket {tid} already exists in {root}: pass --force to replace it")
        if "-legacy-" not in tid:  # never delete anything that is not an import
            raise FileExistsError(f"refusing to replace {dest}")
        shutil.rmtree(dest)
    try:
        _build(export_dir, dest, tid)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return tid


def _build(export_dir: Path, dest: Path, tid: str) -> None:
    src = _read(export_dir / "request.json")
    exported = _read(export_dir / "export.json").get("exported_at") if (export_dir / "export.json").exists() else None
    at = _iso(exported or src["date"])
    started = _iso(src["date"])
    iters = _iteration_numbers(export_dir)
    reviews: dict[int, dict] = {}
    for k in iters:
        rp = export_dir / "iterations" / str(k) / "review.json"
        if rp.exists():
            reviews[k] = _read(rp)

    # request status: the last client decision wins; else the last operator verdict
    decisions = [r["client_approved"] for _, r in sorted(reviews.items()) if r.get("client_approved") is not None]
    if decisions:
        status = "client_approved" if decisions[-1] else "client_changes"
    elif reviews:
        last = reviews[max(reviews)]["verdict"]
        status = "in_review" if last == "ship" else "needs_rework"
    else:
        status = "in_review"
    files = {sid: s["file_name"] for sid, s in (src.get("sources") or {}).items()}
    req = Request(id=tid, created_at=started, text=src["text"], target_duration_s=src.get("target_duration_s"),
                  files=files, status=status)
    tickets._write(dest / "request.json", req.model_dump())

    sdir = dest / "sessions" / "1"
    tickets._write(sdir / "meta.json", SessionMeta(started_at=started, agent=AGENT, model=None).model_dump())
    if (export_dir / "intent.json").exists():
        raw = _read(export_dir / "intent.json")
        known = {k: v for k, v in raw.items() if k in Intent.model_fields}
        tickets._write(sdir / "intent.json", Intent(**known).model_dump())
    for name in ("transcript.jsonl", "timeline.md", "code_changes.md"):
        if (export_dir / name).exists():
            shutil.copy2(export_dir / name, sdir / name)

    skipped: dict[str, str] = {}
    for k in iters:
        idir = sdir / "iterations" / str(k)
        idir.mkdir(parents=True, exist_ok=True)
        comp = export_dir / "iterations" / str(k) / "composition.json"
        if comp.exists():
            shutil.copy2(comp, idir / "composition.json")
        skipped[f"iterations/{k}/plan.json"] = ("export has no maps/ (recut.legacy needs the segment map to "
                                                "resolve clip bounds): not converted")
        if k in reviews:
            tickets._write(idir / "review.json", _review(k, reviews[k]).model_dump())
    if reviews:  # session review.json = latest iteration's review (tickets.save_review convention)
        last = max(reviews)
        tickets._write(sdir / "review.json", _review(last, reviews[last]).model_dump())

    lines = []
    for k in iters:
        r = reviews.get(k)
        if r is not None and r.get("client_approved") is not None:
            fb = ClientFeedback(at=at, session=1, iteration=k,
                                decision="approved" if r["client_approved"] else "changes",
                                rating=None, note=FEEDBACK_NOTE, channel="manual")
            lines.append(fb.model_dump_json())
    if lines:
        (dest / tickets.CLIENT_FILE).write_text("\n".join(lines) + "\n")

    tickets._write(sdir / "import.json", {
        "export": export_dir.name, "exported_at": exported, "skipped": skipped,
        "note": "imported by `recut ticket import-legacy`; baseline = agent `legacy-pre-refactor`",
    })


def _review(k: int, r: dict) -> Review:
    """Review fields only; `human_fix` is folded into the note, `client_approved` is not a review field."""
    note = r.get("note")
    if r.get("human_fix"):
        note = f"{note}\nhuman fix: {r['human_fix']}" if note else f"human fix: {r['human_fix']}"
    return Review(iteration=k, verdict=r["verdict"], splices=r.get("splices") or {},
                  tags=r.get("tags") or [], note=note)
