# Improvement Loop

How session data turns into better software. Run it **weekly** (the first run is on day 7)
with the strongest model, in a fresh session. The operator approves every change.

## Input
- `recut report --json --since <date of last run>`
- `docs/LEARNINGS.md` (create it on the first run)
- For each of the worst sessions in the report: `review.json`, `timeline` from
  `events.jsonl`, and `transcript.jsonl` (read only the parts around the failed
  iterations)

## Procedure
1. **Pick the top 3 problems** from the report. Rank them by how many sessions they cost,
   not by how interesting they are.
2. For each one, decide **where the fix belongs** using its tag group:

   | Tag group | Fix goes into | Example |
   |---|---|---|
   | validator-catchable, or "validator misses" | a new or tighter rule in `src/recut/validator/` | splices marked `off_beat` that the downbeat rule missed → tighten the tolerance |
   | judgement | `skills/cutting/` or `skills/music-theory/` docs | agents keep ending on a chorus with full drums → add an exit rule with an example |
   | `fx_wrong` | the cutting skill's effect recipes (levels, EQ on returns), or a better device (e.g. convolution reverb) | reverb wash squashes the limiter → low-cut the return, lower the send |
   | engine | a new primitive / Clip field | `missing_primitive` on partial fades → issue #53 |
   | analysis | the map pipeline (`src/analysis/`, `make_map.py`) | segment boundaries wrong on track X |
   | intent_misread | the intake form or `intent.json` instructions | "keep the drop" was read as "keep the chorus" |

3. **Write a proposal** for each fix: the evidence (session ids + quotes), the change, and
   how it will be checked. Wait for the operator's OK.
4. **Turn the failing case into a regression fixture**: copy the ticket's request, maps
   and the bad plan into `tests/fixtures/regressions/<ticket_id>/`, and add a test showing
   the fix catches or prevents it. Every fix comes with a test.
5. **Update `docs/LEARNINGS.md`**: one line per fix, in the form
   `- <rule in plain words> (sessions: <ids>, fix: <commit>)`.
   This file is curated: merge or remove lines instead of only appending. Keep it under
   ~60 lines so cutting agents can afford to read it.
6. Add a Log entry to `docs/STATUS.md` with the before/after success rate from the report.

## Principle
Every fix must improve recut **in general** (AGENTS.md, "Core principle"). One session's
failure is evidence for a general cause: fix the cause, not the session.

## What not to do
- Don't change the skills or the validator based on a single session unless the operator
  asks.
- Don't tune for one track. Check that the fix makes sense musically in general.
- Don't add raw session notes to `LEARNINGS.md`. Only distilled rules go there.
