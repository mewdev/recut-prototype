# Workstream B — Backend (tickets, API, SSE, share links, CLI)

**State after the thin slice (2026-11-13):** `src/recut/tickets.py` and
`src/recut/server/app.py` exist: B1 is done, B2 is done except the share routes, B3 is
done (SSE by polling mtimes every 0.5 s, no `watchfiles`), and B4 is done (peaks served
on request, not written as files). The `recut ticket new|list|work|iterate|render|demo`
and `recut serve` commands exist. Left: B5, the transcript hook in B6, and B7.

**Read first:** `AGENTS.md` → `docs/PLAN.md` §3 → this file → `docs/STATUS.md`.
**Owns:** `src/recut/server/`, `src/recut/tickets.py`, the `recut ticket …` CLI commands, `scripts/hooks/`.
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
- `PUT .../review` sets the ticket status: `fixable`/`reject` → `needs_rework`, `ship` → stays `in_review` until it's shared (PLAN §3.1).
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
- `scripts/hooks/copy_transcript.sh` (not under `.claude/`, which is git-ignored) is a Claude Code Stop hook that copies the session
  transcript to `$RECUT_SESSION/transcript.jsonl`.
- Done when: CLI tests pass and the hook is documented in AGENTS.md.

### B7 — `recut report`
`recut report [--since YYYY-MM-DD] [--json]` reads every ticket and prints the numbers the
weekly improvement pass (`docs/IMPROVEMENT_LOOP.md`) works from. It only reads files and
never writes anything.

Definitions (use exactly these):
- A **session** has a **result**: the verdict of its latest `review.json`. Sessions with
  no review count as `unreviewed` and are left out of rates.
- **Success** means the result is `ship`.
- **Iterations to ship**: the iteration number in the `ship` review.
- **Multi-song**: the latest iteration's `plan.json` has more than one source.
- **Model**: `meta.json.model`.

Output sections:
1. **Success rate**: overall, per model, and single-song vs. multi-song. For each:
   `n`, `ship`, `fixable`, `reject`, success %, median iterations to ship.
2. **Failure tags**: counts of every tag (splice tags + overall tags, across all reviewed
   iterations), sorted descending. Group them as:
   - **analysis**: `map_wrong`
   - **engine**: `missing_primitive`, `artifact`
   - **validator-catchable**: `off_beat`, `harmonic_clash`, `abrupt`, `duration_miss`
   - **judgement**: `intent_misread`, `wrong_section`, `energy_drop`, `bad_ending`
3. **Validator misses**: splices you marked bad that had **no** validator issue in
   `render.json`. These are the best candidates for new validator rules.
4. **Worst sessions** (top 5): most iterations without a `ship`, then most bad splices.
   Each shows the ticket id, model, tags, the operator's note, and the GUI link
   `http://localhost:8000/t/<ticket_id>`.

`--json` prints the same data as one JSON object, for agents to read.
- Done when: `pytest tests/report -q` passes against a fixture with ≥4 tickets covering
  ship/fixable/reject, single- and multi-song, two models, and one unreviewed session.

## Out of scope
Authentication (share tokens are the only access control), databases (the folders *are*
the store), and deployment (the operator runs Cloudflare Tunnel by hand).
