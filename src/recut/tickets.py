"""Ticket store: plain folders under .appdata/tickets/ (PLAN §3.1). The folders ARE the database.

<ticket_id>/
  request.json
  inputs/<source_id>.<ext>        maps/<source_id>.json
  sessions/<n>/meta.json  events.jsonl  review.json
  sessions/<n>/iterations/<k>/plan.json  render.json | render_error.json  audio.wav
"""

import json
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import soundfile as sf

from recut.contracts import Plan, Request, Review, SessionMeta
from recut.engine import PlanError, render_plan
from recut.paths import TICKETS_DIR

_B32 = "abcdefghijklmnopqrstuvwxyz234567"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)  # atomic: the server never reads a half-written file


def ticket_dir(ticket_id: str, root: Path = TICKETS_DIR) -> Path:
    d = root / ticket_id
    if not (d / "request.json").exists():
        raise FileNotFoundError(f"ticket not found: {ticket_id}")
    return d


# ---- tickets ------------------------------------------------------------------


def create_ticket(
    text: str,
    files: list[tuple[str, bytes | Path]],
    target_duration_s: Optional[float] = None,
    client_name: Optional[str] = None,
    client_contact: Optional[str] = None,
    root: Path = TICKETS_DIR,
) -> str:
    """files: (original filename, bytes or path). Sources get ids a, b, c, ..."""
    ticket_id = datetime.now().strftime("%Y%m%d-") + "".join(secrets.choice(_B32) for _ in range(4))
    d = root / ticket_id
    (d / "inputs").mkdir(parents=True)
    names = {}
    for i, (name, content) in enumerate(files):
        sid = chr(ord("a") + i)
        dest = d / "inputs" / f"{sid}{Path(name).suffix.lower()}"
        if isinstance(content, Path):
            shutil.copy2(content, dest)
        else:
            dest.write_bytes(content)
        names[sid] = Path(name).name
    req = Request(id=ticket_id, created_at=now(), text=text, target_duration_s=target_duration_s,
                  client_name=client_name, client_contact=client_contact, files=names)
    _write(d / "request.json", req.model_dump())
    return ticket_id


def load_request(ticket_id: str, root: Path = TICKETS_DIR) -> Request:
    return Request.model_validate_json((ticket_dir(ticket_id, root) / "request.json").read_text())


def set_status(ticket_id: str, status: str, root: Path = TICKETS_DIR) -> None:
    req = load_request(ticket_id, root)
    req.status = status  # type: ignore[assignment]
    _write(ticket_dir(ticket_id, root) / "request.json", req.model_dump())


def list_tickets(root: Path = TICKETS_DIR) -> list[Request]:
    if not root.exists():
        return []
    out = [Request.model_validate_json(p.read_text()) for p in root.glob("*/request.json")]
    return sorted(out, key=lambda r: r.created_at, reverse=True)


def sources(ticket_id: str, root: Path = TICKETS_DIR) -> dict[str, dict]:
    """Source id → {input, map (or None)} — what an agent puts into plan.sources."""
    d = ticket_dir(ticket_id, root)
    out = {}
    for f in sorted((d / "inputs").iterdir()):
        m = d / "maps" / f"{f.stem}.json"
        out[f.stem] = {"file": f"inputs/{f.name}", "map": f"maps/{f.stem}.json" if m.exists() else None}
    return out


def ensure_maps(ticket_id: str, root: Path = TICKETS_DIR, analyze=None) -> list[str]:
    """Analyze (Modal) + map every input without a map. Returns the source ids it mapped.

    `analyze(audio_path) -> MusicMap` is injectable for tests; default uses the Modal pipeline.
    """
    d = ticket_dir(ticket_id, root)
    done = []
    for sid, s in sources(ticket_id, root).items():
        if s["map"]:
            continue
        if analyze is None:
            from recut.analysis_client import analyze_to_map as analyze
        music_map = analyze(d / s["file"])
        _write(d / "maps" / f"{sid}.json", music_map.model_dump())
        done.append(sid)
    return done


# ---- sessions & iterations ----------------------------------------------------------


def _git_sha() -> Optional[str]:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True, cwd=Path(__file__).parent).stdout.strip()
    except Exception:
        return None


def session_numbers(ticket_id: str, root: Path = TICKETS_DIR) -> list[int]:
    d = ticket_dir(ticket_id, root) / "sessions"
    return sorted(int(p.name) for p in d.iterdir() if p.name.isdigit()) if d.exists() else []


def iteration_numbers(ticket_id: str, n: int, root: Path = TICKETS_DIR) -> list[int]:
    d = ticket_dir(ticket_id, root) / "sessions" / str(n) / "iterations"
    return sorted(int(p.name) for p in d.iterdir() if p.name.isdigit()) if d.exists() else []


def session_dir(ticket_id: str, n: int, root: Path = TICKETS_DIR) -> Path:
    return ticket_dir(ticket_id, root) / "sessions" / str(n)


def iteration_dir(ticket_id: str, n: int, k: int, root: Path = TICKETS_DIR) -> Path:
    return session_dir(ticket_id, n, root) / "iterations" / str(k)


def new_session(ticket_id: str, agent: Optional[str] = None, model: Optional[str] = None,
                root: Path = TICKETS_DIR) -> int:
    n = (session_numbers(ticket_id, root) or [0])[-1] + 1
    meta = SessionMeta(started_at=now(), agent=agent, model=model, recut_git_sha=_git_sha())
    _write(session_dir(ticket_id, n, root) / "meta.json", meta.model_dump())
    set_status(ticket_id, "in_progress", root)
    return n


def latest_plan(ticket_id: str, root: Path = TICKETS_DIR) -> Optional[dict]:
    for n in reversed(session_numbers(ticket_id, root)):
        for k in reversed(iteration_numbers(ticket_id, n, root)):
            p = iteration_dir(ticket_id, n, k, root) / "plan.json"
            if p.exists():
                return json.loads(p.read_text())
    return None


def new_iteration(ticket_id: str, n: int, plan: Optional[dict] = None,
                  root: Path = TICKETS_DIR) -> int:
    """New iteration k in session n. Starts from `plan`, else a copy of the latest plan."""
    k = (iteration_numbers(ticket_id, n, root) or [0])[-1] + 1
    plan = plan if plan is not None else latest_plan(ticket_id, root)
    d = iteration_dir(ticket_id, n, k, root)
    d.mkdir(parents=True)
    if plan is not None:
        _write(d / "plan.json", plan)
    return k


def log_event(ticket_id: str, n: int, event: dict, root: Path = TICKETS_DIR) -> None:
    p = session_dir(ticket_id, n, root) / "events.jsonl"
    with p.open("a") as f:
        f.write(json.dumps({"ts": now(), **event}) + "\n")


def is_stale(ticket_id: str, n: int, k: int, root: Path = TICKETS_DIR) -> bool:
    d = iteration_dir(ticket_id, n, k, root)
    plan = d / "plan.json"
    if not plan.exists():
        return False
    outs = [p for p in (d / "render.json", d / "render_error.json") if p.exists()]
    return not outs or max(p.stat().st_mtime for p in outs) < plan.stat().st_mtime


def render_iteration(ticket_id: str, n: int, k: int, root: Path = TICKETS_DIR) -> dict:
    """Render plan.json → audio.wav + render.json, or render_error.json. Logs to events.jsonl."""
    d = iteration_dir(ticket_id, n, k, root)
    t0 = time.time()
    err_path = d / "render_error.json"
    try:
        plan = Plan.model_validate_json((d / "plan.json").read_text())
        audio, info = render_plan(plan, ticket_dir(ticket_id, root))
    except (PlanError, ValueError) as e:  # pydantic ValidationError is a ValueError
        msg = str(e)
        _write(err_path, {"message": msg, "at": now()})
        (d / "render.json").unlink(missing_ok=True)
        log_event(ticket_id, n, {"op": "render", "iteration": k, "error": msg,
                                 "duration_ms": int((time.time() - t0) * 1000)}, root)
        return {"error": msg}
    tmp = d / "audio.tmp.wav"
    sf.write(tmp, audio.samples.T, audio.sr, subtype="PCM_16")
    tmp.replace(d / "audio.wav")
    data = info.to_json()
    _write(d / "render.json", data)
    err_path.unlink(missing_ok=True)
    log_event(ticket_id, n, {
        "op": "render", "iteration": k, "duration_ms": int((time.time() - t0) * 1000),
        "duration_s": round(info.duration_s, 3),
        "issues": [f"{i.severity}:{i.rule}" for i in info.issues],
    }, root)
    if load_request(ticket_id, root).status in ("new", "in_progress", "needs_rework"):
        set_status(ticket_id, "in_review", root)
    return data


def render_stale(ticket_id: str, root: Path = TICKETS_DIR) -> list[tuple[int, int]]:
    done = []
    for n in session_numbers(ticket_id, root):
        for k in iteration_numbers(ticket_id, n, root):
            if is_stale(ticket_id, n, k, root):
                render_iteration(ticket_id, n, k, root)
                done.append((n, k))
    return done


# ---- review ------------------------------------------------------------------------


def save_review(ticket_id: str, n: int, review: Review, root: Path = TICKETS_DIR) -> None:
    """Every iteration keeps its own review (iterations/<k>/review.json); the session's
    review.json is a copy of the latest one saved (what the next agent session reads)."""
    review.reviewed_at = now()
    _write(iteration_dir(ticket_id, n, review.iteration, root) / "review.json", review.model_dump())
    _write(session_dir(ticket_id, n, root) / "review.json", review.model_dump())
    log_event(ticket_id, n, {"op": "review", "iteration": review.iteration,
                             "verdict": review.verdict}, root)
    set_status(ticket_id, "needs_rework" if review.verdict != "ship" else "in_review", root)


def load_review(ticket_id: str, n: int, root: Path = TICKETS_DIR) -> Optional[Review]:
    """Latest review saved in session n."""
    p = session_dir(ticket_id, n, root) / "review.json"
    return Review.model_validate_json(p.read_text()) if p.exists() else None


def load_iteration_review(ticket_id: str, n: int, k: int, root: Path = TICKETS_DIR) -> Optional[Review]:
    p = iteration_dir(ticket_id, n, k, root) / "review.json"
    if p.exists():
        return Review.model_validate_json(p.read_text())
    latest = load_review(ticket_id, n, root)  # reviews saved before per-iteration storage
    return latest if latest and latest.iteration == k else None


# ---- demo ------------------------------------------------------------------------------


def create_demo_ticket(root: Path = TICKETS_DIR) -> str:
    """Ticket from examples/summer-party with two rendered iterations — for trying the GUI."""
    ex = Path(__file__).resolve().parents[2] / "examples" / "summer-party"
    if not ex.exists():
        raise FileNotFoundError(f"example bundle not found: {ex}")
    import numpy as np

    from recut.audio import Audio

    tid = create_ticket(
        "Demo: make a ~45s version that ends properly — keep the hook, use the song's real ending.",
        [("summer-party.mp3", ex / "summer-party.mp3")], target_duration_s=45, root=root,
    )
    d = root / tid
    # source b: the same song at -6 dB, to demo a two-source medley
    au = Audio.load(str(ex / "summer-party.mp3"))
    sf.write(d / "inputs" / "b.wav", (np.asarray(au.samples) * 0.5).T, au.sr, subtype="PCM_16")
    req = load_request(tid, root)
    req.files["b"] = "summer-party (-6 dB copy).wav"
    _write(d / "request.json", req.model_dump())
    (d / "maps").mkdir()
    for sid in ("a", "b"):
        shutil.copy2(ex / "summer-party-map.json", d / "maps" / f"{sid}.json")
    n = new_session(tid, agent="demo", model=None, root=root)
    for name in ("01-medley.json", "02-ending-transplant.json"):
        k = new_iteration(tid, n, json.loads((ex / "plans" / name).read_text()), root=root)
        render_iteration(tid, n, k, root)
    return tid
