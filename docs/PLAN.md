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
| Hosting (week 1) | **Mac + named Cloudflare Tunnel on `app.<operator's domain>`** (the domain's DNS moves to Cloudflare, free). **Cloudflare Access** (email login, only the operator) protects everything except the client paths (§3.6). Move to a Hetzner VPS (same Docker setup) once clients depend on it. | Free, HTTPS, permanent share links, no billing risk. Without Access, anyone guessing a ticket id could open client audio and transcripts. |
| Multi-song | **In scope.** Week 1: sequencing (medley A→B, several versions of the same song). Mashup/layering: the plan format has **tracks** from day 1, but only one track (+ returns + master) renders in week 1. Week 2 adds multi-track mixing and stem separation (clients send full mixes only). | Real tickets failed here and needed a human. Tracks now avoid a rewrite later. |
| Tempo mismatch | **Choose compatible join points** (breakdowns, outros, longer crossfades). No time-stretching in week 1. | Matches what the human did by hand. |
| Loudness | **Auto LUFS-match** every source at load time (pyloudnorm). | Removes the "volume jumps at the splice" class of failures. |
| Effects API | **Ableton-style model (D1 contract, built in A7 + A8):** tracks, clip gain and fade handles, devices (inserts), sends to return tracks, automation as ramps or breakpoints, musical time units (`"1/8."`, `"2 bars"`), dB, and percentages as Ableton shows them. It replaces the `*Sweep` classes and the earlier `ring_out`/`scope` idea. | The operator thinks in Ableton, and LLM agents know DAW vocabulary far better than recut-specific names, which means fewer plan mistakes. |
| Ending transplant | **In scope for week 1 (task A7).** The operator's most common manual fix: take the ending from the end of the same song and place it mid-song. Done three ways: (1) the ending hit lands on top while the previous part's tail rings out, (2) a reverb wash on the last beat(s) going into the ending, (3) a normal crossfade + reverb. Needs `compose()` to place clips on a timeline and add up overlaps, plus sends to a reverb return. | Single-song, already the main cause of manual work. The timeline core is also what week-2 layering needs. |
| Validator, cross-song splice | Downbeat alignment (**error**), BPM gap > ~3% and not near 2:1 (warn), key not Camelot-adjacent (warn), short-term loudness jump across the splice (warn). | |
| Feedback unit | **Per splice**: ok/bad + tags. **Overall**: verdict `ship`/`fixable`/`reject` + a note. | Splices are where cuts fail. |
| Success metric | **Primary:** operator ships the agent's cut with zero edits. **Check:** the client approves it on the share link. | The operator's verdict stands in for the client's; client approval confirms it. |
| Agent loop | Claude Code works on a ticket folder: reads `request.json` and the latest `review.json`, writes new iterations. No agent inside the GUI in week 1. | |
| Client visibility | Clients see a cut **only after the operator marks it `ship`**: unguessable share link, no accounts, player with original vs. cut, plus an Approve / Request-changes button. | |
| Intake | Free-text request + target duration. | |
| Data | Ticket folders in git-ignored `.appdata/tickets/`, synced nightly to cloud storage (R2 or Drive). **Client audio never goes into git.** | |

**Principle (operator, 2026-11-13):** every code or architecture change is a general
improvement, never a workaround for one session, track or ticket. Sessions are evidence
for general causes (AGENTS.md, "Core principle").

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
      render.json              # 3.3 (or render_error.json {message, at} if the plan can't render)
      audio.wav
      review.json              # 3.5, this iteration's review (session review.json = latest copy)
    review.json                # 3.5 (operator, per session's latest iteration)
  share.json                   # {token, session, iteration, created_at, client_decision?, client_note?}
  client_feedback.jsonl        # one ClientFeedback per client reaction (decision, rating 1–5, note, channel); append-only
  events.jsonl                 # ticket-level timeline (L1), append-only: {ts, op, ...} with op in
                               #   created | status (from,to) | session_started (n, model) | rendered (n,k)
                               #   | reviewed (n,k,verdict) | shipped (n,k) | shared (n,k) | client_feedback (decision, rating)
  sessions/<n>/usage.json      # L1: {model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                               #   cost_usd (estimated, null if unknown model), duration_s, turns} summed from transcript.jsonl
```

`status`: `new → in_progress → in_review → (needs_rework → in_progress → in_review)* → shipped → client_approved | client_changes`.

Saving a review with verdict `fixable` or `reject` sets `needs_rework`. In week 1 the
operator restarts the agent by hand (`recut ticket work <id>`). Later, a watcher can start
an agent on every `needs_rework` ticket automatically, so the operator only reviews.
Nothing in these formats needs to change for that.

### 3.2 Plan v2 (`plan.json`): Ableton-style session

The plan reads like a small Ableton arrangement: **tracks** hold clips, clips have
**gain** and **fade handles**, **devices** sit on a clip, a track or the master,
**sends** feed **return tracks** (reverb/delay live there), and any device parameter or
send can be **automated**. Clips are still chosen musically (section + bars/beats from
the map); free timecodes are not allowed.

```json
{
  "version": 2,
  "sources": {
    "a": {"file": "inputs/a.mp3", "map": "maps/a.json"},
    "b": {"file": "inputs/b.mp3", "map": "maps/b.json"}
  },
  "returns": [
    {"id": "A", "name": "Reverb", "devices": [
      {"id": "verb", "type": "reverb", "decay": "3.5s", "pre_delay": "20ms",
       "size": 80, "hi_cut": 6000, "dry_wet": 100}]},
    {"id": "B", "name": "Delay", "devices": [
      {"id": "dly", "type": "delay", "time": "1/8.", "feedback": 35, "ping_pong": true,
       "filter_lo": 300, "filter_hi": 5000, "dry_wet": 100}]}
  ],
  "tracks": [
    {"id": "main", "volume": 0, "pan": 0, "devices": [], "clips": [
      {"id": "n1", "type": "clip", "source": "a", "segment": "intro", "index": 1,
       "fade_in": {"length": "1 beat", "shape": "linear"}},
      {"id": "n2", "type": "clip", "source": "a", "segment": "chorus", "index": 1, "bars": 8},
      {"id": "x1", "type": "xfade", "length": "4 beats", "shape": "equal_power"},
      {"id": "n3", "type": "clip", "source": "b", "segment": "chorus", "index": 2, "gain": -1.5,
       "devices": [{"id": "flt", "type": "auto_filter", "filter": "lowpass",
                    "frequency": 20000, "resonance": 0.2}],
       "automation": [{"target": "devices.flt.frequency", "points": [["0 beats", 20000], ["2 bars", 800]],
                       "shape": "exp"}]},
      {"id": "n4", "type": "clip", "source": "b", "segment": "verse", "index": 2, "bars": 4,
       "sends": {"A": "-inf"},
       "automation": [{"target": "sends.A", "from": "-inf", "to": 0, "over": "1 beat",
                       "at": "end", "shape": "exp"}]},
      {"id": "x2", "type": "xfade", "length": "30ms", "out_shape": "hold", "in_shape": "equal_power"},
      {"id": "n5", "type": "clip", "source": "b", "segment": "outro", "index": 1,
       "fade_out": {"length": "2 bars", "shape": "exp"}}
    ]}
  ],
  "master": {"devices": [{"id": "lim", "type": "limiter", "ceiling": -1}]},
  "target_duration_s": 150
}
```

`n4 → x2 → n5` is an **ending transplant** (variant 2, "reverb wash into the ending"): the
send to the reverb return opens on the verse's last beat, the song's real outro lands on
top, and the wash keeps ringing on the return.

**Units:** one rule per kind of value, so agents can't mix them up.
| Kind | Written as | Examples |
|---|---|---|
| Time | string with a unit. Musical units follow the source's tempo. | `"1/4"`, `"1/8."` (dotted), `"1/8t"` (triplet), `"3 beats"`, `"2 bars"`, `"250ms"`, `"3.5s"` |
| Level (`gain`, `volume`, sends, `ceiling`, EQ gain) | number in **dB**, or `"-inf"` | `-6`, `0`, `"-inf"` |
| Percentage (`dry_wet`, `feedback`, `size`, `width`) | number 0–100, as Ableton shows it | `dry_wet: 40` |
| Frequency | number in Hz | `frequency: 800`, `hi_cut: 6000` |
| Pan | -50 (L) … 50 (R), as Ableton shows it | `pan: 0` |
| Shape (fades, xfades, automation) | `linear` · `equal_power` · `exp` · `log` · `hold` | old name `qsin` is accepted as `equal_power` |

**Clip fields:**
- Selection fields stay as today: `source`, `segment`, `index`, `bars`/`beats`,
  `offset_bars`/`offset_beats`, `loop`.
- `gain` (dB), `fade_in` / `fade_out` (`{length, shape}`) are the clip's fade handles.
- `devices` (an insert chain), `sends` (`{return_id: dB}`) and `automation`.

**Joins (`xfade`):** `length` and `shape`, or `out_shape` / `in_shape` per side.
`"hold"` keeps that side at full level for the whole overlap.
- variant 1, hit on top + tail rings: the outgoing clip has a send open, and the
  join is a short `xfade` with `in_shape: "hold"`.
- a short overlap with both sides at full level: `out_shape` and `in_shape` both
  `"hold"`.

**Devices (week 1)**, with Ableton names; parameters as in the example:
| Device | Parameters |
|---|---|
| `utility` | `gain`, `width` |
| `eq` | `low_cut`, `high_cut` (Hz), `bands: [{frequency, gain, q}]` |
| `auto_filter` | `filter: lowpass, highpass or bandpass`, `frequency`, `resonance` |
| `reverb` | `decay`, `pre_delay`, `size`, `hi_cut`, `width`, `dry_wet` |
| `delay` | `time` (synced, e.g. `"1/8."`, or ms), `feedback`, `ping_pong`, `filter_lo`, `filter_hi`, `dry_wet` |
| `limiter` | `ceiling` |

Reverb runs on pedalboard's Freeverb, so `decay` is approximate: it's mapped to room
size, and the engine docs give the table.

**Automation:** each entry is either a **ramp** or **points**.
- Ramp: `{target, from, to, over, at: "start" | "end" | "<time from clip start>", shape}`
- Points: `{target, points: [[time from clip start, value], ...], shape}`
- Targets: `gain`, `sends.<return_id>`, `devices.<device_id>.<param>`.
- Clips, tracks and returns can carry automation.

**Rules:**
- Return tracks keep ringing after clips end, so reverb and delay tails are never cut
  off. That's why there's no special "ring out" field.
- Week 1 renders exactly **one** track plus returns and master. More than one track
  raises `ValueError("multi-track not supported yet")`.
- Old-format compositions (`Fade`, `Reverb`, `ReverbSweep`, `Delay`, `FilterSweep`,
  `XFade(ms, curve)`) still load through an adapter in the engine, and the test suite
  covers it.

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
     "cross_source": true, "overlap_ms": 2069, "out_shape": "equal_power",
     "in_shape": "equal_power"}
  ],
  "issues": [
    {"severity": "warn", "rule": "bpm_gap", "splice": "s1", "node": null,
     "message": "a 116 BPM → b 124 BPM (6.9%)"}
  ],
  "sources": {"a": {"bpm": 116, "key": "F#m", "lufs_in": -9.1, "lufs_target": -14}},
  "automation": [{"node_id": "n4", "target": "sends.A", "out_start": 52.1, "out_end": 52.6}],
  "returns_tail_end": 61.0,
  "peak_dbfs": -1.2,
  "limiter_applied": false
}
```

Segments can overlap in output time (crossfades). `out_time` is the point where the
incoming clip starts. `automation` lists where in the output each automation is active, so
the GUI can draw it. `returns_tail_end` is where the last reverb/delay tail dies out.

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
- `fx_wrong`: an effect or its settings sound wrong (reverb too loud/squashed, wrong type, bad automation). Added 2026-11-13 after the first real review.

### 3.6 API (FastAPI)

```
POST /api/tickets                         multipart: files + text + target_duration_s  (client upload)
GET  /api/tickets                         list + status
GET  /api/tickets/{id}                    request + sessions + iterations
GET  /api/tickets/{id}/sessions/{n}/iterations/{k}      plan + render.json
GET  /media/tickets/{id}/...              audio (originals + renders), Range requests supported
GET  /api/tickets/{id}/events             SSE: "changed" (renders stale iterations first)
GET  /api/tickets/{id}/maps/{source_id}   music map as strict JSON (NaN → null)
GET  /api/tickets/{id}/peaks/{path}?n=    waveform min/max peaks for any audio file in the ticket
PUT  /api/tickets/{id}/sessions/{n}/review
POST /api/tickets/{id}/share              {session?, iteration?} → {token, url}  (409 unless verdict == ship;
                                          default: newest shipped iteration; base URL = RECUT_PUBLIC_URL)
GET  /s/{token}                           client page: Cut/Original player, Approve / Request changes, 1-5 stars, comment, consent line; 404 page for unknown tokens
GET  /s/{token}/audio/cut                 shared render only (Range requests)
GET  /s/{token}/audio/original            shared original only (Range requests)
POST /api/share/{token}/decision          {approved: bool, rating?: 1-5, note?}  → client_feedback.jsonl (channel share_page)
POST /api/tickets                         (also public: the client upload form)
```

**Public paths** (no login): `/new`, `POST /api/tickets`, `/s/*`, `/api/share/*`, and the
frontend's static assets. **Everything else is behind Cloudflare Access** (operator
only). The client page must never reference `/media/...` or ticket ids.

```
```

Waveform peaks: the server computes them on request (`/peaks/...`, cached in memory).
The browser doesn't decode the whole file just to draw it.

## 3.7 Data: where it lives, what's logged, training-ready

**Storage (operator decision 2026-11-14).** All ticket data is saved to the private repo
**`mewdev/recut-data`**, permanently and automatically:
- recut uses `<recut-data checkout>/tickets` whenever a `recut-data` clone sits next to
  this repo. That's the same on the Mac (`~/Documents/dev/`) and in cloud sessions
  (`/home/user/`). `RECUT_TICKETS_DIR` overrides it.
- Every ticket action commits and pushes (`recut.sync`): `recut ticket new|work|iterate|render|demo`,
  the review server (new ticket, render, review), and the transcript Stop hook.
  `RECUT_AUTOSYNC=0` turns it off; `recut sync` syncs by hand.
- Audio is never committed. Back it up separately.
- Pre-ticket sessions live in `recut-data/baseline/pre-refactor/` (old format), as the
  "before" for comparisons.

**Measured for the improvement pass and for presenting results.** Each metric needs these
logs; the task that adds missing logs is noted.
| Metric | Needs | Status |
|---|---|---|
| Ship rate (operator verdict), first-attempt ship rate, iterations to ship | per-iteration reviews | ✅ (`recut report`) |
| Failure tags, validator misses, check accuracy | reviews + render issues | ✅ |
| Results per model (Sonnet / Opus / …) | `meta.json.model` | ✅ |
| **Client approval rate**, client change requests, **satisfaction 1–5** + comment | share link + client page | ❌ B5+ |
| **Turnaround**: request → first cut → shipped → client decision | ticket-level status events with timestamps | ❌ L1 |
| **Cost per cut** (tokens/€ per ticket and model), session duration | transcript usage summed | ❌ L1 |
| Human interventions (manual fixes, code fixes per ticket) | review `human_fix`, linked PRs | ❌ L1 |
| Trend before/after each improvement pass, presentation page | all of the above + baseline import | ❌ L2 (`recut report --html`), L3 (import baseline) |

**Training-ready (a specialised cutting model may be trained on this later).** Keep every
format versioned with stable ids. The data then yields:
- (request, map) → shipped plan: supervised examples
- worse vs. better iteration of the same ticket: preference pairs
- per-join ok/bad + tags: a join-quality scorer
- client approval: the true target

Still to add, without blocking anything now:
- audio *features* around each join (spectra, loudness, beat alignment ±2 s), not audio
- a client-consent line on the upload page ("edits may be used, anonymised, to improve
  the service")
- `recut dataset export` later

The licences of the analysis models matter more for a commercially used model (see the
README).

## 4. Week schedule

| Day | Work |
|---|---|
| 1 | Operator + 1 agent: finalize §3 schemas as Pydantic models + an OpenAPI stub + a fixture ticket (summer-party + a 2-song medley). |
| 2–5 | Three agents in separate git worktrees (below). |
| 6 | Integration: real tickets end to end, through the Cloudflare Tunnel. |
| 7 | Run 5–10 real tickets, review them, and do the first improvement pass from the tags. |

**Workstream A — engine** (`src/recut/`)
- Plan v2 parser.
- Multi-source `compose()` over a single track.
- Ableton-style timeline engine: returns, sends, devices, automation (A7, A8).
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

## 4a. Which model does what (budget)

The rule: **expensive models write the contracts and tests, cheap models make the tests
pass.** Cheap models fail by guessing. Frozen contracts, small tasks, and a "Done when"
command for each task (see `docs/workstreams/`) leave them nothing to guess.

| Work | Model | Why |
|---|---|---|
| D1 contracts (incl. the unit parser `recut.contracts.units`) + fixture ticket, I1 integration, reviewing PRs/diffs between workstreams | strongest (Opus) | Mistakes here spread to every workstream |
| Workstream tasks (A2–A5, B2–B3, C3–C6) | Sonnet | Multi-file work with music/DSP or UI subtleties |
| Mechanical tasks (A1, A6, B1, B4–B6, C1–C2, C7), tests, docs updates | Haiku | Clearly specified, bounded by tests |
| Open-weights models (via OpenCode/Aider, which read `AGENTS.md`) | only Haiku-tier tasks | Fine for small single-file tasks with tests; unreliable for multi-file changes |
| **Cutting agent** on tickets (the product itself) | start with Sonnet; try cheaper later | `meta.json.model` records the model, so success rate can be compared per model from the logged data |

How to save tokens:
- One task per agent session. Start fresh for the next task: context grows with every
  turn and costs more.
- Agents read only `AGENTS.md`, `docs/PLAN.md` §3, their brief and `docs/STATUS.md`,
  not the whole repo.
- `docs/STATUS.md` is the handoff between sessions, so nothing is lost when a session
  ends.

## 5. After week 1 (not in scope now)

- Inspector editing saved as correction diffs.
- Multi-track mixing + stem separation (Demucs on Modal) for mashups.
- Time-stretch.
- A replay eval suite built from failed tickets.
- Hands-off rework loop: a watcher starts an agent on every `needs_rework` ticket, so the
  operator only reviews (see §3.1 status).
- The weekly improvement pass starts on day 7 (not deferred). The procedure is in
  `docs/IMPROVEMENT_LOOP.md`, and it uses `recut report` (task B7).
- A curated `docs/LEARNINGS.md`.
- Hetzner VPS.
- The customer-facing agent in a sandbox.

## 6. Open risks

- **Licensing:** MuQ (CC BY-NC) and Essentia (AGPLv3) are fine for private
  testing but block a paid hosted service. See `README.md`.
- Chord and segment timestamps can differ by a few hundred ms. The downbeat rule
  must use the beat grid, not segment boundaries.
- Ending transplants make overlapping audio add up, which can clip. A7 adds a master
  limiter (only applied when the peak exceeds -1 dBFS); `peak_clip` was replaced by `qc_limiting` (Q1).
- Old docs (preview architecture notes, mockup comments) say xfade isn't wired
  in and there are no effects. Both are outdated: `XFade` and
  Fade/Reverb/Delay/FilterSweep already work.
