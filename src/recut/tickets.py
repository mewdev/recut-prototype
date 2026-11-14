"""Ticket store: plain folders under .appdata/tickets/ (PLAN §3.1). The folders ARE the database.

<ticket_id>/
  request.json
  inputs/<source_id>.<ext>        maps/<source_id>.json
  sessions/<n>/meta.json  events.jsonl  review.json
  sessions/<n>/iterations/<k>/plan.json  render.json | render_error.json  audio.wav
"""

import json
import os
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import soundfile as sf

from recut.contracts import ClientFeedback, Intent, Plan, Request, Review, SessionMeta, Share
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


TIMELINE_FILE = "events.jsonl"


def ticket_event(ticket_id: str, op: str, root: Path = TICKETS_DIR, **fields) -> None:
    """Append one `{ts, op, ...}` line to the ticket-level timeline (`<ticket>/events.jsonl`)."""
    p = root / ticket_id / TIMELINE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps({"ts": now(), "op": op, **fields}) + "\n")


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
    with (d / TIMELINE_FILE).open("a") as f:
        f.write(json.dumps({"ts": req.created_at, "op": "created"}) + "\n")
    return ticket_id


INTAKE_FILE = "intake.json"


def record_intake(ticket_id: str, checks: list[tuple[str, "IntakeResult"]], override: bool,  # noqa: F821
                  root: Path = TICKETS_DIR) -> None:
    """Keep the intake problems and the operator's override: `<ticket>/intake.json` + a timeline event.

    Not in request.json: the `Request` contract is frozen and forbids extra fields. `checks` is
    [(original filename, IntakeResult)]; files are keyed by source id (a, b, ...) like request.files.
    """
    files = {}
    for i, (name, res) in enumerate(checks):
        files[chr(ord("a") + i)] = {"name": name, **res.to_dict()}
    problems = [{"file": name, **p} for name, res in checks for p in res.problems]
    _write(root / ticket_id / INTAKE_FILE, {"override": override, "problems": problems, "files": files})
    ticket_event(ticket_id, "intake", root, problems=problems, override=override)


def load_request(ticket_id: str, root: Path = TICKETS_DIR) -> Request:
    return Request.model_validate_json((ticket_dir(ticket_id, root) / "request.json").read_text())


def set_status(ticket_id: str, status: str, root: Path = TICKETS_DIR) -> None:
    req = load_request(ticket_id, root)
    old = req.status
    req.status = status  # type: ignore[assignment]
    _write(ticket_dir(ticket_id, root) / "request.json", req.model_dump())
    if old != status:
        ticket_event(ticket_id, "status", root, **{"from": old, "to": status})


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
    ticket_event(ticket_id, "session_started", root, n=n, agent=agent, model=model)
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


def mark_current_session(ticket_id: str, n: int, root: Path = TICKETS_DIR) -> None:
    """Remember the session being worked on, for the transcript hook (scripts/hooks/copy_transcript.sh):
    a Claude Code hook can't see an `export` made inside an agent's shell, so it falls back to
    this pointer file."""
    (root / CURRENT_SESSION_FILE).write_text(str(session_dir(ticket_id, n, root).resolve()) + "\n")


CURRENT_SESSION_FILE = ".current_session"
STARTER_NOTES_PREFIX = "starter plan"  # `recut ticket work` seeds plan.notes with this


def _previous_plan(ticket_id: str, n: int, k: int, root: Path) -> Optional[dict]:
    """The plan this iteration follows: iteration k-1 of the session, or for the first
    iteration of a session the last plan of an earlier session."""
    if k > 1:
        p = iteration_dir(ticket_id, n, k - 1, root) / "plan.json"
        return json.loads(p.read_text()) if p.exists() else None
    for m in reversed([s for s in session_numbers(ticket_id, root) if s < n]):
        for j in reversed(iteration_numbers(ticket_id, m, root)):
            p = iteration_dir(ticket_id, m, j, root) / "plan.json"
            if p.exists():
                return json.loads(p.read_text())
    return None


def process_warnings(ticket_id: str, n: int, k: int, root: Path = TICKETS_DIR) -> list[str]:
    """Agent-process reminders for iteration k of session n (AGENTS.md, "Working a client ticket"):
    `intent.json` written before cutting, and `plan.notes` saying what changed and why. Shown by
    `recut ticket render`; they are not render issues (render.json stays as the engine wrote it)."""
    out: list[str] = []
    ip = session_dir(ticket_id, n, root) / "intent.json"
    if not ip.exists():
        out.append(f"no intent.json for session {n}: write how you read the request BEFORE cutting "
                   f"({ip}); fields: target_duration_s, must_keep, must_cut, ending, notes")
    else:
        try:
            Intent.model_validate_json(ip.read_text())
        except ValueError as e:
            out.append(f"intent.json is not valid ({ip}): {str(e).splitlines()[0]}")
    pp = iteration_dir(ticket_id, n, k, root) / "plan.json"
    if pp.exists():
        notes = (json.loads(pp.read_text()).get("notes") or "").strip()
        prev = _previous_plan(ticket_id, n, k, root)
        prev_notes = ((prev or {}).get("notes") or "").strip()
        if not notes or notes.lower().startswith(STARTER_NOTES_PREFIX):
            out.append("plan.notes is empty: write what you changed and why in plan.notes "
                       "(it is the only record of your reasoning)")
        elif prev is not None and notes == prev_notes:
            out.append("plan.notes are identical to the previous iteration's: write what you "
                       "changed and why in plan.notes")
    return out


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
        ticket_event(ticket_id, "rendered", root, n=n, k=k, error=msg)
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
    ticket_event(ticket_id, "rendered", root, n=n, k=k, duration_s=round(info.duration_s, 3))
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
    ticket_event(ticket_id, "reviewed", root, n=n, k=review.iteration, verdict=review.verdict)
    if review.verdict == "ship":
        ticket_event(ticket_id, "shipped", root, n=n, k=review.iteration)
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


# ---- client feedback ----------------------------------------------------------------------

CLIENT_FILE = "client_feedback.jsonl"


def _shipped_iteration(ticket_id: str, n: int, root: Path) -> Optional[int]:
    """Latest iteration of session n whose review verdict is ship."""
    for k in reversed(iteration_numbers(ticket_id, n, root)):
        rv = load_iteration_review(ticket_id, n, k, root)
        if rv is not None and rv.verdict == "ship":
            return k
    return None


def _default_target(ticket_id: str, root: Path) -> tuple[int, int]:
    """Where a client reaction attaches when none is given: the latest shipped iteration, else the
    latest iteration of the latest session."""
    sessions = session_numbers(ticket_id, root)
    for n in reversed(sessions):
        k = _shipped_iteration(ticket_id, n, root)
        if k is not None:
            return n, k
    for n in reversed(sessions):
        ks = iteration_numbers(ticket_id, n, root)
        if ks:
            return n, ks[-1]
    raise ValueError(f"ticket {ticket_id} has no iterations yet: nothing for the client to react to")


def add_client_feedback(ticket_id: str, decision: str, rating: Optional[int] = None,
                        note: Optional[str] = None, session: Optional[int] = None,
                        iteration: Optional[int] = None, channel: str = "manual",
                        root: Path = TICKETS_DIR) -> ClientFeedback:
    """Record one client reaction (append-only `client_feedback.jsonl`), log it to the session's
    events and set the ticket status (client_approved / client_changes).

    Attaches to the latest shipped iteration unless `session` and/or `iteration` are given. A bare
    `session` means that session's shipped (else latest) iteration; a bare `iteration` means the
    latest session that has it."""
    if session is None and iteration is None:
        n, k = _default_target(ticket_id, root)
    elif session is None:
        candidates = [n for n in session_numbers(ticket_id, root)
                      if iteration in iteration_numbers(ticket_id, n, root)]
        if not candidates:
            raise ValueError(f"no iteration {iteration} in ticket {ticket_id}")
        n, k = candidates[-1], iteration
    else:
        ks = iteration_numbers(ticket_id, session, root)
        if not ks:
            raise ValueError(f"no session {session} in ticket {ticket_id}")
        n = session
        k = iteration if iteration is not None else (_shipped_iteration(ticket_id, n, root) or ks[-1])
        if k not in ks:
            raise ValueError(f"no iteration {k} in session {n} of ticket {ticket_id}")

    fb = ClientFeedback(at=now(), session=n, iteration=k, decision=decision, rating=rating,
                        note=(note or "").strip() or None, channel=channel)
    with (ticket_dir(ticket_id, root) / CLIENT_FILE).open("a") as f:
        f.write(fb.model_dump_json() + "\n")
    log_event(ticket_id, n, {"op": "client_feedback", "iteration": k, "decision": decision,
                             "rating": rating, "channel": fb.channel}, root)
    ticket_event(ticket_id, "client_feedback", root, n=n, k=k, decision=decision, rating=rating)
    set_status(ticket_id, "client_approved" if decision == "approved" else "client_changes", root)
    return fb


def load_client_feedback(ticket_id: str, root: Path = TICKETS_DIR) -> list[ClientFeedback]:
    """Every client reaction for the ticket, in the order they were recorded."""
    p = ticket_dir(ticket_id, root) / CLIENT_FILE
    if not p.exists():
        return []
    return [ClientFeedback.model_validate_json(line) for line in p.read_text().splitlines() if line.strip()]


def ticket_timeline(ticket_id: str, root: Path = TICKETS_DIR) -> list[dict]:
    """The ticket's events in time order: the real ones from `events.jsonl` plus entries derived
    (`"derived": true`) from the timestamps older tickets already carry (request.created_at,
    session meta.started_at, review.reviewed_at, client feedback `at`). A derived entry is
    dropped when a real event covers the same thing, so new tickets show only real events."""
    d = ticket_dir(ticket_id, root)
    real: list[dict] = []
    p = d / TIMELINE_FILE
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict) and "ts" in ev and "op" in ev:
                real.append(ev)

    def key(ev: dict):
        op = ev["op"]
        if op == "created":
            return (op,)
        if op == "session_started":
            return (op, ev.get("n"))
        if op == "client_feedback":
            return (op, ev.get("n"), ev.get("k"), ev.get("decision"))
        return (op, ev.get("n"), ev.get("k"))

    have = {key(e) for e in real}
    derived: list[dict] = []

    def add(ev: dict) -> None:
        if key(ev) not in have:
            derived.append({**ev, "derived": True})

    add({"ts": load_request(ticket_id, root).created_at, "op": "created"})
    for n in session_numbers(ticket_id, root):
        meta = session_dir(ticket_id, n, root) / "meta.json"
        try:
            m = SessionMeta.model_validate_json(meta.read_text())
            add({"ts": m.started_at, "op": "session_started", "n": n, "agent": m.agent, "model": m.model})
        except (OSError, ValueError):
            pass
        for k in iteration_numbers(ticket_id, n, root):
            rv = load_iteration_review(ticket_id, n, k, root)
            if rv is not None and rv.reviewed_at:
                add({"ts": rv.reviewed_at, "op": "reviewed", "n": n, "k": k, "verdict": rv.verdict})
                if rv.verdict == "ship":
                    add({"ts": rv.reviewed_at, "op": "shipped", "n": n, "k": k})
    for fb in load_client_feedback(ticket_id, root):
        add({"ts": fb.at, "op": "client_feedback", "n": fb.session, "k": fb.iteration,
             "decision": fb.decision, "rating": fb.rating})
    return sorted(real + derived, key=lambda e: e["ts"])  # stable: real before derived on ties
# ---- client share link ------------------------------------------------------------------

SHARE_FILE = "share.json"


def load_share(ticket_id: str, root: Path = TICKETS_DIR) -> Optional[Share]:
    """The ticket's current share (one token at a time), or None."""
    p = ticket_dir(ticket_id, root) / SHARE_FILE
    return Share.model_validate_json(p.read_text()) if p.exists() else None


def find_share(token: str, root: Path = TICKETS_DIR) -> Optional[tuple[str, Share]]:
    """(ticket id, share) for a token, or None. Compares in constant time."""
    for req in list_tickets(root):
        sh = load_share(req.id, root)
        if sh and secrets.compare_digest(sh.token, token):
            return req.id, sh
    return None


def create_share(ticket_id: str, session: Optional[int] = None, iteration: Optional[int] = None,
                 root: Path = TICKETS_DIR) -> Share:
    """Share a `ship`-reviewed iteration with the client (default: the newest shipped one).

    Sharing the iteration that is already shared reuses its token; a different one gets a new
    token (share.json holds only the current share). Raises ValueError unless the verdict is ship."""
    sessions = session_numbers(ticket_id, root)
    if session is None and iteration is None:
        target = next(((n, k) for n in reversed(sessions)
                       if (k := _shipped_iteration(ticket_id, n, root)) is not None), None)
        if target is None:
            raise ValueError("no iteration has a ship verdict yet: review one as ship first")
        n, k = target
    else:
        n = session if session is not None else next(
            (m for m in reversed(sessions) if iteration in iteration_numbers(ticket_id, m, root)), None)
        if n is None or n not in sessions:
            raise ValueError("no such session/iteration")
        ks = iteration_numbers(ticket_id, n, root)
        k = iteration if iteration is not None else (_shipped_iteration(ticket_id, n, root) or (ks[-1] if ks else None))
        if k not in ks:
            raise ValueError("no such session/iteration")
        rv = load_iteration_review(ticket_id, n, k, root)
        if rv is None or rv.verdict != "ship":
            raise ValueError(f"s{n}·it{k} is not reviewed as ship: only shipped cuts can be shared")
    if not (iteration_dir(ticket_id, n, k, root) / "audio.wav").exists():
        raise ValueError(f"s{n}·it{k} has no rendered audio")
    cur = load_share(ticket_id, root)
    if cur and (cur.session, cur.iteration) == (n, k):
        return cur
    sh = Share(token=secrets.token_urlsafe(16), session=n, iteration=k, created_at=now())
    _write(ticket_dir(ticket_id, root) / SHARE_FILE, sh.model_dump())
    log_event(ticket_id, n, {"op": "shared", "iteration": k}, root)
    ticket_event(ticket_id, "shared", root, n=n, k=k)
    return sh


def record_share_decision(ticket_id: str, share: Share, approved: bool, rating: Optional[int],
                          note: Optional[str], root: Path = TICKETS_DIR) -> ClientFeedback:
    """A client's answer from the share page: appended as feedback for the shared s/k and mirrored
    in share.json."""
    fb = add_client_feedback(ticket_id, "approved" if approved else "changes", rating=rating,
                             note=note, session=share.session, iteration=share.iteration,
                             channel="share_page", root=root)
    share.client_decision, share.client_note = fb.decision, fb.note
    _write(ticket_dir(ticket_id, root) / SHARE_FILE, share.model_dump())
    return fb


def share_url(token: str, base: Optional[str] = None) -> str:
    base = base or os.environ.get("RECUT_PUBLIC_URL") or "http://localhost:8000"
    return f"{base.rstrip('/')}/s/{token}"


def is_demo(ticket_id: str, root: Path = TICKETS_DIR) -> bool:
    """Demo/test tickets (`recut ticket demo`): no real client, never counted as awaiting."""
    meta = session_dir(ticket_id, 1, root) / "meta.json"
    try:
        return json.loads(meta.read_text()).get("agent") == "demo"
    except (OSError, ValueError):
        return False


def awaiting_client(root: Path = TICKETS_DIR) -> list[dict]:
    """Shipped cuts with no client reaction recorded since they were shipped.

    A ticket is awaiting when its newest `ship` review is newer than its newest client
    feedback (or it has none). Demo tickets are skipped. Newest ship first.
    """
    out = []
    for req in list_tickets(root):
        if is_demo(req.id, root):
            continue
        shipped = None  # (reviewed_at, n, k)
        for n in session_numbers(req.id, root):
            for k in iteration_numbers(req.id, n, root):
                r = load_iteration_review(req.id, n, k, root)
                if r and r.verdict == "ship" and r.reviewed_at and (shipped is None or r.reviewed_at > shipped[0]):
                    shipped = (r.reviewed_at, n, k)
        if shipped is None:
            continue
        feedback = load_client_feedback(req.id, root)
        if feedback and max(f.at for f in feedback) >= shipped[0]:
            continue
        out.append({"id": req.id, "shipped_at": shipped[0], "session": shipped[1],
                    "iteration": shipped[2], "text": req.text})
    return sorted(out, key=lambda x: x["shipped_at"], reverse=True)


def awaiting_client_message(root: Path = TICKETS_DIR) -> str:
    """Operator reminder text (CLI, server start, SessionStart hook). Empty when nothing waits."""
    items = awaiting_client(root)
    if not items:
        return ""
    lines = [f"REMINDER: {len(items)} shipped cut(s) have no client feedback recorded yet. "
             "When the client answers, log it (it's what the client approval rate is built from):"]
    for it in items:
        lines.append(f"  - {it['id']} (s{it['session']}·it{it['iteration']}, shipped {it['shipped_at'][:10]}): "
                     f"{it['text'][:60]}")
        lines.append(f"    recut ticket client {it['id']} --approved|--changes --rating 1-5 --note \"what the client said\"")
    return "\n".join(lines)


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
