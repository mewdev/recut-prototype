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
| D1 contracts (`src/recut/contracts/`) + fixture ticket | done | units parser, plan/render/ticket models; demo ticket = `recut ticket demo` |
| A1 plan v2 loader | done | pydantic `Plan` in contracts (strict: unknown fields are errors) |
| A2 multi-source compose | done | `src/recut/engine.py` (timeline, not concatenation) |
| A3 LUFS match | todo | |
| A4 render.json | done | `engine.render_plan` → `RenderInfo` |
| A5 cross-song validator rules | todo | |
| A6 session logging | partial | the server/CLI log renders + reviews to `events.jsonl`; `RECUT_SESSION` for direct `compose()` calls is still todo |
| A7 timeline engine: tracks, joins, returns/sends, master | done | `engine.py`, `devices.py` (reverb + limiter), `automation.py` (gain/send ramps + points). Tests: `tests/engine/test_timeline.py` |
| A8 devices, automation, old-format adapter, skill docs | todo | Sonnet, after A7 |
| B1 ticket store | done | `src/recut/tickets.py` |
| B2 FastAPI app | done (no share routes) | `src/recut/server/app.py`, `recut serve` |
| B3 SSE live reload | done | polling, renders stale iterations |
| B4 waveform peaks | done | on request, cached in memory |
| B5 share links | todo | |
| B6 CLI + transcript hook | partial | CLI done; hook todo (put it in `scripts/hooks/`) |
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
- Music maps can contain `NaN` loudness (zero-length segments), which isn't valid JSON for
  browsers. The server works around it (`/api/tickets/{id}/maps/{sid}`), but `make_map`
  should not produce NaN (analysis code, operator's call).

## Decisions
- 2026-11-13 — Level automation (`gain`, `sends.*`, volume) interpolates in the linear gain
  domain with the shape warping progress, so `-inf → 0` + `exp` swells from silence. Before a
  ramp starts the curve holds its `from`, after it ends its `to`; automation overrides the
  static `gain`/send value. Sends are post-fader (after clip gain, fades, xfade ramps).
- 2026-11-13 — The Freeverb `reverb` device: `decay` → room_size via a measured table
  (`devices.REVERB_DECAY_TABLE`, 0.53–9.5 s), `size` scales decay (x0.7…x1.3), the wet signal
  is level-compensated so `dry_wet: 100` is about as loud as the input.
- 2026-11-13 — Legacy xfade path: `render_plan(..., _legacy_xfades={node_id: (ms, curve)})`
  is an internal argument (not in the contract) that reproduces the old overlap length and
  old curves, including `qsin` out = `1 - sin`. Only `recut.legacy` (A8) should pass it.
- 2026-11-13 — Thin slice first (operator's request): D1 + engine + tickets + server + a
  no-build page, so the operator can pull and test before the workstreams fill in.
- 2026-11-13 — Renders are `audio.wav` (fast, lossless); mp3 only for client share links later.
- 2026-11-13 — The master `limiter` scales the output to `ceiling`: pedalboard's Limiter
  normalizes to 0 dBFS on its own.
- 2026-11-13 — The old `xfade` `qsin` fade-out is `1 - sin` (equal-gain), not `cos`
  (equal-power). The new engine's `equal_power` is real equal power. The A8 old-format
  adapter must keep the old curve to reproduce saved compositions exactly.
- 2026-11-13 — Merged `fix/song-edge-snapping` (the last segment runs to the end of the
  audio). The bundled `summer-party` map predates the fix: its last ~5 s (the fade-out)
  sit in a zero-length `silence` segment and can't be used until the map is regenerated.

## Log
- 2026-11-13 — A7 done. Clip `sends` feed one buffer per return; the return's chain runs once
  over the whole timeline (+10 s pad), the tail is cut where it falls below -60 dBFS
  (`returns_tail_end`), track `volume`/constant-power `pan`, master chain, `peak_dbfs` (output
  level, after the master) and `limiter_applied`. Gain and send automation render per sample.
  `not_rendered` warnings are gone for sends/returns/automation; clip/track devices other
  than reverb/limiter still warn until A8. 144 tests pass.
- 2026-11-13 — D1 + thin slice done. Contracts in `src/recut/contracts/`; engine
  `src/recut/engine.py`; ticket store `src/recut/tickets.py`; review server
  `src/recut/server/` (`recut serve`); CLI `recut ticket ...`. 136 tests pass. Tested in
  headless Chromium: live re-render on a plan.json save keeps the playhead, a broken plan
  shows the error, a review saves and sets `needs_rework`.
- 2026-11-13 — Effects API switched to an Ableton-style model before D1: tracks, clip
  gain/fade handles, devices, sends → return tracks, automation (ramps + points), musical
  units, dB. Replaces `ring_out`/`scope`. A7 rewritten, A8 added. Unit parser moved into D1.
- 2026-11-13 — Added A7 (ending transplant: overlaps, ring-out, scoped fx, limiter) and the
  hosting decision (named tunnel on the operator's domain + Cloudflare Access; share-page
  audio routes). The plan format was extended before D1, so nothing frozen was broken.
- 2026-11-12 — Plan, workstream briefs and this log created. Waiting on: the operator's
  past-session export (prompt in chat) and contracts day (D1).
