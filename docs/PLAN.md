# recut — 1-Week Prototype Plan

Decisions from the planning ("grill") session, plus the contracts every build
agent works against. **Read this before building anything in the workstreams
below.** If you need to change a contract (§3), update this file first.

## 1. Goal

Clients send tracks plus an edit request, which becomes a **ticket**. An agent
cuts it. The operator reviews it in a browser GUI (original vs. cut, timeline,
which parts were joined) and leaves feedback on each splice. Approved cuts go to
the client through a share link. Every session is logged so agents can improve.
Today about 30% of cuts succeed; the point of this prototype is to measure and
raise that.

## 2. Decisions

| Topic | Decision | Why |
|---|---|---|
| GUI purpose (week 1) | **Review station**: play/A-B original vs. cut, a timeline showing which source parts were joined, validator hits, per-splice feedback. Editing in the inspector comes in week 2 and is saved as a *correction* diff, never as a silent change. | Precise feedback is the learning signal. Silent edits would pollute the agent's success data. |
| Preview engine | **Server render + reload.** Python `compose()` renders the file, the browser plays it, and the server pushes an update over SSE so the player reloads at the same playhead. **No WebAudio engine, FAUST or preview-schedule IR for now.** | Measured: composing a 62s cut takes 0.06s and writing it 0.07s. One engine means preview and final render can't drift apart. |
| Stack | **React** (reuse `recut-wireframe.tsx`, shadcn) + **FastAPI** JSON API around the recut library. | The mockup is already most of the layout, and agents build React/shadcn reliably. |
| Hosting (week 1) | **Mac + Cloudflare Tunnel.** Move to a Hetzner VPS (same Docker setup) once clients depend on it. | Free, HTTPS, no billing risk. |
| Multi-song | **In scope.** Week 1: sequencing (medley A→B, several files of the same song). Mashup/layering: the plan format has **lanes** from day 1, but only one lane renders in week 1. Week 2 adds multi-lane mixing and stem separation (clients send full mixes only). | Real tickets failed here and needed a human. Lanes now avoid a rewrite later. |
| Tempo mismatch | **Choose compatible join points** (breakdowns, outros, longer crossfades). No time-stretching in week 1. | Matches what the human did by hand. |
| Loudness | **Auto LUFS-match** every source at load time (pyloudnorm). | Removes the "volume jumps at the splice" class of failures. |
| Validator, cross-song splice | Downbeat alignment (**error**), BPM gap > ~3% and not near 2:1 (warn), key not Camelot-adjacent (warn), short-term loudness jump across the splice (warn). | |
| Feedback unit | **Per splice**: ok/bad + tags. **Overall**: verdict `ship`/`fixable`/`reject` + a note. | Splices are where cuts fail. |
| Success metric | **Primary:** operator ships the agent's cut with zero edits. **Check:** the client approves it on the share link. | The operator's verdict stands in for the client's; client approval confirms it. |
| Agent loop | Claude Code works on a ticket folder: reads `request.json` and the latest `review.json`, writes new iterations. No agent inside the GUI in week 1. | |
| Client visibility | Clients see a cut **only after the operator marks it `ship`**: unguessable share link, no accounts, player with original vs. cut, plus an Approve / Request-changes button. | |
| Intake | Free-text request + target duration. | |
| Data | Ticket folders in git-ignored `.appdata/tickets/`, synced nightly to cloud storage (R2 or Drive). **Client audio never goes into git.** | |

**Cut list if the week slips:** inspector editing (already week 2), then public
hosting (localhost only). The client upload page, the full validator and
multi-song sequencing all stay in.

## 3. Contracts (agree on these on day 1, then build in parallel)

### 3.1 Ticket folder

```
.appdata/tickets/<ticket_id>/
  request.json                 # {id, created_at, client_name, client_contact, text, target_duration_s, status}
  inputs/<source_id>.<ext>     # uploaded tracks; maps built via recut analyze/map
  sessions/<n>/
    meta.json                  # {started_at, agent, recut_git_sha, skills_version}
    intent.json                # agent's structured reading of the request (written BEFORE cutting)
    events.jsonl               # auto-logged by the library (see 3.4)
    transcript.jsonl           # Claude Code transcript, copied by a Stop hook
    iterations/<k>/
      plan.json                # 3.2
      render.json              # 3.3
      audio.mp3
    review.json                # 3.5 (operator, per session's latest iteration)
  share.json                   # {token, session, iteration, created_at, client_decision?, client_note?}
```

`status`: `new → in_progress → in_review → shipped → client_approved | client_changes`.

### 3.2 Plan v2 (`plan.json`)

This is the existing `Clip`/`XFade` model, extended with named sources and lanes.
It keeps the musical units (sections, bars, beats); free timecodes are not allowed.

```json
{
  "version": 2,
  "sources": {
    "a": {"file": "inputs/a.mp3", "map": "maps/a.json"},
    "b": {"file": "inputs/b.mp3", "map": "maps/b.json"}
  },
  "lanes": [
    {"id": "main", "gain_db": 0, "nodes": [
      {"id": "n1", "type": "clip", "source": "a", "segment": "intro", "index": 1},
      {"id": "n2", "type": "clip", "source": "a", "segment": "chorus", "index": 1, "bars": 8},
      {"id": "x1", "type": "xfade", "beats": 4, "curve": "qsin"},
      {"id": "n3", "type": "clip", "source": "b", "segment": "chorus", "index": 2,
       "offset_beats": 0, "fx": [{"type": "fade", "vol_start": 1, "vol_end": 0, "curve": "qsin"}]}
    ]}
  ],
  "target_duration_s": 150
}
```

Week 1: `compose()` raises an error if there is more than one lane. Clip field
names follow `recut.compositor.nodes.Clip`.

### 3.3 Render output (`render.json`)

This is what the GUI needs to draw "what the cut did". It is produced by the same `compose()` call that renders the audio.

```json
{
  "duration_s": 148.2,
  "segments": [
    {"node_id": "n2", "source": "a", "label": "chorus#1",
     "src_start": 45.1, "src_end": 61.6, "out_start": 8.3, "out_end": 24.8}
  ],
  "splices": [
    {"id": "s1", "out_time": 24.8, "from": "n2", "to": "n3",
     "cross_source": true, "xfade_ms": 2069, "curve": "qsin"}
  ],
  "issues": [
    {"severity": "warn", "rule": "bpm_gap", "splice": "s1", "node": null,
     "message": "a 116 BPM → b 124 BPM (6.9%)"}
  ],
  "sources": {"a": {"bpm": 116, "key": "F#m", "lufs_in": -9.1, "lufs_target": -14}}
}
```

### 3.4 Session logging

If env `RECUT_SESSION=<path to sessions/<n>>` is set, the **library** (not the
agent) appends one JSON line per `compose`/`validate`/`render` call to
`events.jsonl`: `{ts, op, plan_hash, duration_ms, issues, error}`. Agents don't
need to remember to log.

### 3.5 Review (`review.json`)

```json
{
  "iteration": 3,
  "verdict": "ship | fixable | reject",
  "splices": {"s1": {"ok": false, "tags": ["off_beat"], "note": "lands half a beat late"}},
  "tags": ["duration_miss"],
  "note": "free text",
  "reviewed_at": "..."
}
```

Tag set (fixed, so tags can be counted across sessions):
- `intent_misread`, `wrong_section`, `off_beat`, `harmonic_clash`, `energy_drop`, `abrupt`, `bad_ending`, `duration_miss`, `artifact`
- `map_wrong`: the analysis was wrong
- `missing_primitive`: the engine can't express the right cut

### 3.6 API (FastAPI)

```
POST /api/tickets                         multipart: files + text + target_duration_s  (client upload)
GET  /api/tickets                         list + status
GET  /api/tickets/{id}                    request + sessions + iterations
GET  /api/tickets/{id}/sessions/{n}/iterations/{k}      plan + render.json
GET  /media/tickets/{id}/...              audio (originals + renders), Range requests supported
GET  /api/tickets/{id}/events             SSE: "iteration_created" / "render_updated"
PUT  /api/tickets/{id}/sessions/{n}/review
POST /api/tickets/{id}/share              → {token, url}  (only if verdict == ship)
GET  /s/{token}                           client page: player, original vs. cut
POST /api/share/{token}/decision          {approved: bool, note}
```

Waveform peaks: the server precomputes them for every audio file (`<file>.peaks.json`).
The browser doesn't decode the whole file just to draw it.

## 4. Week schedule

| Day | Work |
|---|---|
| 1 | Operator + 1 agent: finalize §3 schemas as Pydantic models + an OpenAPI stub + a fixture ticket (summer-party + a 2-song medley). |
| 2–5 | Three agents in separate git worktrees (below). |
| 6 | Integration: real tickets end to end, through the Cloudflare Tunnel. |
| 7 | Run 5–10 real tickets, review them, and do the first improvement pass from the tags. |

**Workstream A — engine** (`src/recut/`)
- Plan v2 parser.
- Multi-source `compose()` over a single lane.
- LUFS match on load.
- `render.json` output (segments, splices).
- Cross-song validator rules.
- `RECUT_SESSION` logging.
- Done when: pytest is green and the fixture medley renders with correct segments/splices.

**Workstream B — backend** (`src/recut/server/`)
- Ticket store and FastAPI routes.
- SSE via file watch on `iterations/`.
- Peaks generation.
- Share tokens.
- CLI `recut ticket new|work|list`.
- Claude Code Stop hook that copies the transcript.
- Done when: the API runs against the fixture ticket.

**Workstream C — frontend** (`web/`)
- Replace the mockup's data with API calls.
- Composition view coloured by source, plus a source-map view (source waveform with the used regions highlighted and linked).
- Splice markers with ok/bad + tag popover.
- A/B toggle against the original.
- Verdict panel.
- Problems panel from `issues`.
- Client upload page and share page.
- Remove the inspector editing and the Assistant chat for week 1.
- Done when: a full review can be done in under 30s per cut.

## 5. After week 1 (not in scope now)

- Inspector editing saved as correction diffs.
- Multi-lane mixing + stem separation (Demucs on Modal) for mashups.
- Time-stretch.
- A replay eval suite built from failed tickets.
- A weekly improvement pass: failed tags → validator rule / skill edit / primitive.
- A curated `docs/LEARNINGS.md`.
- Hetzner VPS.
- The customer-facing agent in a sandbox.

## 6. Open risks

- **Licensing:** MuQ (CC BY-NC) and Essentia (AGPLv3) are fine for private
  testing but block a paid hosted service. See `README.md`.
- Chord and segment timestamps can differ by a few hundred ms. The downbeat rule
  must use the beat grid, not segment boundaries.
- Old docs (preview architecture notes, mockup comments) say xfade isn't wired
  in and there are no effects. Both are outdated: `XFade` and
  Fade/Reverb/Delay/FilterSweep already work.
