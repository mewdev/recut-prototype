# Workstream C — Frontend (review GUI, client upload + share pages)

**Read first:** `AGENTS.md` → `docs/PLAN.md` §2–3 → this file → `docs/STATUS.md`.
**Owns:** `web/` only.
**Does not touch:** anything under `src/`. If the API is missing something, add it to
*Blockers* in `docs/STATUS.md`.
**Suggested model:** Sonnet. C1 and C7 are fine for Haiku.

Starting point: `web/reference/recut-wireframe.tsx` (the operator's mockup). Keep its
layout and look. Replace its mock data with API data.

Stack: Vite + React + TypeScript + Tailwind + shadcn/ui + wavesurfer.js (pin exact
versions). Generate types from the backend's OpenAPI with `openapi-typescript` into
`web/src/api/types.ts`. Don't hand-write API types.

Until the backend runs, use a mock server that serves the files in
`tests/fixtures/tickets/medley-demo/` (`web/mock/`).

## Tasks

### C1 — Scaffold
Vite app in `web/`. `npm run dev` proxies `/api` and `/media` to `localhost:8000`.
- Done when: `npm run build` and `npm run typecheck` pass.

### C2 — Ticket list + ticket page
- `/` lists tickets with their status.
- `/t/:id` shows the request text, target duration, sources, and the sessions with their
  iterations; the latest iteration is selected.

### C3 — Composition view (from the mockup's waveform view)
- Segments come from `render.json.segments`, coloured by source, with waveforms from
  `.peaks.json`.
- A crossfade "bowtie" at each splice, using its `overlap_ms`, `out_shape` and `in_shape`
  (draw a flat line for `hold`). Segments can overlap in time, so stack overlapping parts
  in two rows.
- Draw `render.json.automation` as a thin Ableton-style automation strip under the clip it
  belongs to (e.g. "Send A" ramping up). Draw the return tail as a faded band up to
  `returns_tail_end`.
- Playhead, click to seek, zoom. Space toggles play.
- Audio plays through wavesurfer.

### C4 — Source map ("what the cut did")
Below the composition, draw each source's full waveform with the regions used by the cut
highlighted (`src_start`–`src_end`) and labelled with segment names from the map. Draw a
line from each region to its place in the composition. Clicking a region seeks the
composition to that segment.

### C5 — A/B + live reload
- Toggle the player between the cut and the original source, at the matching position:
  in "original" mode, play the source from `src_start + (t - out_start)` of the current
  segment.
- Subscribe to SSE. On `render_updated`, reload the audio and keep the playhead
  position.

### C6 — Review panel (replaces the mockup's Inspector for week 1)
- Every splice marker gets an ok/bad toggle and a tag picker (the tag list in PLAN §3.5)
  plus a note.
- Overall verdict, overall tags and a note.
- Saves with `PUT .../review`.
- The Problems panel lists `render.json.issues`; clicking one jumps to that splice.
- Keyboard: `n`/`p` for next/previous splice, `g`/`b` for ok/bad.
- Target: a full review in under 30 s.
- Remove the mockup's inspector editing and the Assistant chat. Keep the code in
  `web/reference/` for week 2.

### C7 — Client pages
- `/new`: upload form (files, request text, target duration) → `POST /api/tickets` →
  confirmation page.
- `/s/:token`: a simple player (audio only from `/s/{token}/audio/cut|original`) with
  Original / Cut tabs and Approve / Request changes
  (with a note). No operator UI or internal data on this page.
- Must work on a phone.

Done when (all tasks): `npm run build` passes, and the operator can review the fixture
ticket end to end in the browser.
