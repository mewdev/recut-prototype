# Build Status / Handoff Log

**Every agent reads this file before starting and updates it before ending.** It is the
only memory shared between agent sessions. If something isn't written here, the next
agent won't know it.

## Rules
1. When you start a task: set its row to `in_progress` with your workstream letter.
2. When you finish: set it to `done` and add a Log entry (newest at the top).
3. If you're blocked or unsure about a contract, **don't guess**. Add a *Blockers* entry,
   leave the task as `blocked`, and move to the next task you can do.
4. If you made a decision the contracts didn't cover, add it under *Decisions* with one
   line on why.
5. Keep entries short: what changed, files touched, the command that proves it works.

## Tasks

| Task | Status | Notes |
|---|---|---|
| D1 contracts (`src/recut/contracts/`) + fixture ticket | todo | Day 1, operator + strongest model |
| A1 plan v2 loader | todo | |
| A2 multi-source compose | todo | |
| A3 LUFS match | todo | |
| A4 render.json | todo | |
| A5 cross-song validator rules | todo | |
| A6 session logging | todo | |
| A7 timeline engine: tracks, joins, returns/sends, master | todo | Sonnet, after A4. Ending-transplant core |
| A8 devices, automation, old-format adapter, skill docs | todo | Sonnet, after A7 |
| B1 ticket store | todo | |
| B2 FastAPI app | todo | |
| B3 SSE live reload | todo | |
| B4 waveform peaks | todo | |
| B5 share links | todo | |
| B6 CLI + transcript hook | todo | |
| B7 `recut report` | todo | Haiku; needed by day 7 |
| C1 scaffold | todo | |
| C2 ticket list/page | todo | |
| C3 composition view | todo | |
| C4 source map | todo | |
| C5 A/B + live reload | todo | |
| C6 review panel | todo | |
| C7 client pages | todo | |
| I1 integration + real tickets | todo | Day 6–7, strongest model |

## Blockers
_(none)_

## Decisions
_(none yet; see docs/PLAN.md §2 for planning decisions)_

## Log
- 2026-11-13 — Effects API switched to an Ableton-style model before D1: tracks, clip
  gain/fade handles, devices, sends → return tracks, automation (ramps + points), musical
  units, dB. Replaces `ring_out`/`scope`. A7 rewritten, A8 added. Unit parser moved into D1.
- 2026-11-13 — Added A7 (ending transplant: overlaps, ring-out, scoped fx, limiter) and the
  hosting decision (named tunnel on the operator's domain + Cloudflare Access; share-page
  audio routes). The plan format was extended before D1, so nothing frozen was broken.
- 2026-11-12 — Plan, workstream briefs and this log created. Waiting on: the operator's
  past-session export (prompt in chat) and contracts day (D1).
