# Workstream B — Backend (tickets, API, SSE, share links, CLI)

**Read first:** `AGENTS.md` → `docs/PLAN.md` §3 → this file → `docs/STATUS.md`.
**Owns:** `src/recut/server/`, `src/recut/tickets.py`, the `recut ticket …` CLI commands, `.claude/hooks/`.
**Does not touch:** `src/recut/contracts/` (frozen), `src/recut/compositor/`,
`src/recut/validator/`, `web/`.
**Suggested model:** Sonnet. B1, B5 and B6 are fine for Haiku.

Until workstream A merges, use the fixture files in `tests/fixtures/tickets/medley-demo/`
(they already contain `render.json`). Don't call `compose()` directly; go through
`recut.render_iteration()`, and stub it if A isn't done yet.

## Tasks

### B1 — Ticket store
`recut.tickets` has `create_ticket(text, target_duration_s, files) -> id`,
`list_tickets()`, `get_ticket(id)`, `new_session(id)`, `new_iteration(id, n)` and
`set_status`. It uses the folder layout in PLAN §3.1 under `paths.TICKETS_DIR` (add
`.appdata/tickets` to `paths.py`).
- Ticket id: `YYYYMMDD-<4 random base32 chars>`.
- Done when: `pytest tests/tickets -q` passes.

### B2 — FastAPI app
`src/recut/server/app.py` implements every route in PLAN §3.6, using the response
models from `recut.contracts`.
- `/media/...` serves files with HTTP Range support (`FileResponse` does this).
- Add `fastapi`, `uvicorn` and `python-multipart` to `pyproject.toml`.
- Run it with `recut serve --port 8000`.
- Done when: `pytest tests/server -q` passes (`TestClient`, one test per route) and
  `/docs` shows the API.

### B3 — Live reload (SSE)
`GET /api/tickets/{id}/events` sends `iteration_created` and `render_updated` events
when files under the ticket's `sessions/` change. Use `watchfiles`.
- Done when: a test writes a new iteration folder and receives the event within 2 s.

### B4 — Waveform peaks
Whenever a source or render is written, also write `<file>.peaks.json`:
`{"sr": ..., "samples_per_peak": 512, "peaks": [[min, max], ...]}` (mono mixdown).
- Done when: a test checks the length and that values are in [-1, 1].

### B5 — Share links
`POST /api/tickets/{id}/share` returns 409 unless the latest review's verdict is
`ship`. The token is `secrets.token_urlsafe(16)`, stored in `share.json`.
`POST /api/share/{token}/decision` records the client's decision and sets the status.
- Done when: tests cover a 409 for a non-ship verdict, a successful share, and a recorded
  decision.

### B6 — CLI + transcript hook
- `recut ticket new <files...> --text ... --duration ...`
- `recut ticket list`
- `recut ticket work <id>`: creates a new session, writes `meta.json`
  (`agent`, `model`, `recut_git_sha`, `started_at`), and prints the
  `export RECUT_SESSION=...` line plus the paths to the request and latest review for
  the agent.
- `.claude/hooks/copy_transcript.sh` is a Claude Code Stop hook that copies the session
  transcript to `$RECUT_SESSION/transcript.jsonl`.
- Done when: CLI tests pass and the hook is documented in AGENTS.md.

## Out of scope
Authentication (share tokens are the only access control), databases (the folders *are*
the store), and deployment (the operator runs Cloudflare Tunnel by hand).
