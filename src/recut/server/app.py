"""Review server (thin slice of workstream B). Run: `recut serve` → http://localhost:8000

Server-rendered preview: plan.json changes → re-render (~0.1 s) → SSE "changed" → the
browser reloads the audio at the same playhead.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from recut import sync, tickets, usage
from recut.audio import Audio
from recut.contracts import TAGS, Review, Share
from recut.paths import TICKETS_DIR

STATIC = Path(__file__).parent / "static"


class Decision(BaseModel):
    approved: bool
    rating: Optional[int] = Field(None, ge=1, le=5)
    note: Optional[str] = Field(None, max_length=4000)


class ShareRequest(BaseModel):
    session: Optional[int] = None
    iteration: Optional[int] = None


def create_app(root: Path = TICKETS_DIR) -> FastAPI:
    app = FastAPI(title="recut review server")

    def tdir(tid: str) -> Path:
        try:
            return tickets.ticket_dir(tid, root)
        except FileNotFoundError:
            raise HTTPException(404, f"ticket not found: {tid}")

    def safe_path(tid: str, rel: str) -> Path:
        base = tdir(tid).resolve()
        p = (base / rel).resolve()
        if base not in p.parents or not p.is_file():
            raise HTTPException(404, "file not found")
        return p

    # ---- pages ----------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    @app.get("/t/{tid}", response_class=HTMLResponse)
    @app.get("/new", response_class=HTMLResponse)
    def page(tid: Optional[str] = None):
        return (STATIC / "app.html").read_text()

    @app.get("/report", response_class=HTMLResponse)
    def report_page():
        # operator-only like the rest of the app (the public surface is /s/ and /api/share/ only)
        from datetime import datetime

        from recut import report
        from recut.report_html import render_html

        return render_html(report.build(root), generated=datetime.now().strftime("%Y-%m-%d %H:%M"))

    def shared(token: str) -> tuple[str, Share]:
        found = tickets.find_share(token, root)
        if found is None:
            raise HTTPException(404, "link not found")
        return found

    def public_base(request: Request) -> str:
        return os.environ.get("RECUT_PUBLIC_URL") or str(request.base_url).rstrip("/")

    # ---- client share page (public: no ticket ids, no file paths) --------------
    @app.get("/s/{token}", response_class=HTMLResponse)
    def share_page(token: str):
        if tickets.find_share(token, root) is None:
            return HTMLResponse((STATIC / "share_404.html").read_text(), status_code=404)
        return HTMLResponse((STATIC / "share.html").read_text(), headers={"Cache-Control": "no-store"})

    @app.get("/s/{token}/audio/cut")
    def share_cut(token: str):
        tid, sh = shared(token)
        p = tickets.iteration_dir(tid, sh.session, sh.iteration, root) / "audio.wav"
        if not p.is_file():
            raise HTTPException(404, "not found")
        return FileResponse(p, media_type="audio/wav", headers={"Cache-Control": "no-cache"})

    @app.get("/s/{token}/audio/original")
    def share_original(token: str):
        tid, sh = shared(token)
        render_p = tickets.iteration_dir(tid, sh.session, sh.iteration, root) / "render.json"
        srcs = tickets.sources(tid, root)
        used: dict[str, float] = {}
        if render_p.exists():
            for seg in json.loads(render_p.read_text()).get("segments", []):
                used[seg["source"]] = used.get(seg["source"], 0.0) + seg["out_end"] - seg["out_start"]
        sid = max(used, key=used.get) if used else next(iter(srcs), None)
        if sid is None or sid not in srcs:
            raise HTTPException(404, "not found")
        return FileResponse(safe_path(tid, srcs[sid]["file"]), headers={"Cache-Control": "no-cache"})

    @app.post("/api/share/{token}/decision")
    def share_decision(token: str, d: Decision):
        tid, sh = shared(token)
        tickets.record_share_decision(tid, sh, d.approved, d.rating, d.note, root)
        sync.request_sync(f"client feedback {tid} s{sh.session}·it{sh.iteration}", root)
        return {"ok": True}

    @app.post("/api/tickets/{tid}/share")
    def create_share(tid: str, request: Request, body: Optional[ShareRequest] = None):
        tdir(tid)
        body = body or ShareRequest()
        try:
            sh = tickets.create_share(tid, body.session, body.iteration, root)
        except ValueError as e:
            raise HTTPException(409, str(e))
        sync.request_sync(f"share {tid} s{sh.session}·it{sh.iteration}", root)
        return {"token": sh.token, "url": tickets.share_url(sh.token, public_base(request))}

    # ---- api ------------------------------------------------------------------
    @app.get("/api/meta")
    def meta():
        return {"tags": list(TAGS)}

    @app.get("/api/tickets")
    def list_all():
        waiting = {it["id"] for it in tickets.awaiting_client(root)}
        out = []
        for r in tickets.list_tickets(root):
            sessions = tickets.session_numbers(r.id, root)
            review = tickets.load_review(r.id, sessions[-1], root) if sessions else None
            out.append({**r.model_dump(), "sessions": len(sessions),
                        "latest_verdict": review.verdict if review else None,
                        "awaiting_client": r.id in waiting})
        return out

    @app.post("/api/tickets")
    async def create(text: str = Form(...), target_duration_s: Optional[float] = Form(None),
                     client_name: Optional[str] = Form(None), files: list[UploadFile] = File(...)):
        payload = [(f.filename or "upload", await f.read()) for f in files]
        tid = tickets.create_ticket(text, payload, target_duration_s, client_name, root=root)
        sync.request_sync(f"new ticket {tid}", root)
        return {"id": tid}

    @app.get("/api/tickets/{tid}")
    def get_ticket(tid: str, request: Request):
        tdir(tid)
        share = tickets.load_share(tid, root)
        sessions = []
        for n in tickets.session_numbers(tid, root):
            sd = tickets.session_dir(tid, n, root)
            meta_p = sd / "meta.json"
            review = tickets.load_review(tid, n, root)
            its = []
            for k in tickets.iteration_numbers(tid, n, root):
                d = tickets.iteration_dir(tid, n, k, root)
                it_review = tickets.load_iteration_review(tid, n, k, root)
                its.append({"k": k, "has_plan": (d / "plan.json").exists(),
                            "review": it_review.model_dump() if it_review else None,
                            "rendered": (d / "render.json").exists(),
                            "error": (d / "render_error.json").exists()})
            sessions.append({"n": n, "meta": json.loads(meta_p.read_text()) if meta_p.exists() else None,
                             "review": review.model_dump() if review else None, "iterations": its,
                             "usage": usage.load_usage(sd)})
        return {"request": tickets.load_request(tid, root).model_dump(),
                "sources": tickets.sources(tid, root), "sessions": sessions,
                "timeline": tickets.ticket_timeline(tid, root),
                "share": ({**share.model_dump(), "url": tickets.share_url(share.token, public_base(request))}
                          if share else None),
                "client_feedback": [fb.model_dump() for fb in tickets.load_client_feedback(tid, root)]}

    @app.get("/api/tickets/{tid}/sessions/{n}/iterations/{k}")
    def get_iteration(tid: str, n: int, k: int):
        tdir(tid)
        d = tickets.iteration_dir(tid, n, k, root)
        if not d.exists():
            raise HTTPException(404, "iteration not found")
        if tickets.is_stale(tid, n, k, root):
            tickets.render_iteration(tid, n, k, root)
            sync.request_sync(f"render {tid} s{n}·it{k}", root)

        def read(name):
            p = d / name
            return json.loads(p.read_text()) if p.exists() else None

        audio = d / "audio.wav"
        return {"plan": read("plan.json"), "render": read("render.json"),
                "error": read("render_error.json"),
                "audio_version": int(audio.stat().st_mtime * 1000) if audio.exists() else None}

    @app.put("/api/tickets/{tid}/sessions/{n}/review")
    def put_review(tid: str, n: int, review: Review):
        tdir(tid)
        tickets.save_review(tid, n, review, root)
        sync.request_sync(f"review {tid} s{n}·it{review.iteration} {review.verdict}", root)
        return {"ok": True, "status": tickets.load_request(tid, root).status}

    @app.get("/api/tickets/{tid}/maps/{sid}")
    def get_map(tid: str, sid: str):
        """Music map as strict JSON (maps can contain NaN loudness, which browsers reject)."""
        data = json.loads(safe_path(tid, f"maps/{sid}.json").read_text())
        return _no_nan(data)

    @app.get("/api/tickets/{tid}/peaks/{rel:path}")
    def peaks(tid: str, rel: str, n: int = 1600):
        return _peaks(safe_path(tid, rel), max(100, min(n, 8000)))

    @app.get("/media/tickets/{tid}/{rel:path}")
    def media(tid: str, rel: str):
        return FileResponse(safe_path(tid, rel), headers={"Cache-Control": "no-cache"})

    @app.get("/api/tickets/{tid}/events")
    async def events(tid: str, request: Request):
        """SSE. Renders stale iterations, emits `changed` whenever anything under sessions/ moves."""
        base = tdir(tid)

        def signature():
            files = sorted((base / "sessions").rglob("*")) if (base / "sessions").exists() else []
            return tuple((str(p), p.stat().st_mtime) for p in files
                         if p.is_file() and not p.name.endswith(".tmp") and ".tmp." not in p.name)

        async def stream():
            last = None
            yield "retry: 1000\n\n"
            while not await request.is_disconnected():
                rendered = await asyncio.to_thread(tickets.render_stale, tid, root)
                if rendered:
                    sync.request_sync(f"render {tid}", root)
                sig = await asyncio.to_thread(signature)
                if sig != last:
                    if last is not None:
                        yield "event: changed\ndata: {}\n\n"
                    last = sig
                await asyncio.sleep(0.5)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    return app


def _no_nan(x):
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
        return None
    if isinstance(x, dict):
        return {k: _no_nan(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_no_nan(v) for v in x]
    return x


_PEAKS: dict[tuple[str, float, int], dict] = {}


def _peaks(path: Path, n: int) -> dict:
    key = (str(path), path.stat().st_mtime, n)
    if key not in _PEAKS:
        try:
            data, sr = sf.read(path, dtype="float32", always_2d=True)
            mono = data.mean(axis=1)
        except Exception:  # mp3 etc. → librosa
            au = Audio.load(str(path))
            sr = au.sr
            mono = np.asarray(au.samples).mean(axis=0) if au.samples.ndim == 2 else au.samples
        buckets = np.array_split(mono, n) if len(mono) >= n else [mono]
        mins = [float(b.min()) if len(b) else 0.0 for b in buckets]
        maxs = [float(b.max()) if len(b) else 0.0 for b in buckets]
        _PEAKS[key] = {"duration_s": len(mono) / sr, "min": [round(v, 4) for v in mins],
                       "max": [round(v, 4) for v in maxs]}
    return _PEAKS[key]


app = create_app()
