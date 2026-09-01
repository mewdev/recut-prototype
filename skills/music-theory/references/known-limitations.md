# Known Limitations

recut is an early prototype (see repo `CLAUDE.md`). Say these gaps out loud when
relevant rather than silently treating a judgment call as ground truth.

## No harmonic function in the map

`ChordEntry` (`src/recut/map/schema.py`) has exactly three fields: `start`, `end`,
`chord` — a raw `root:quality` string (`C:maj7`). No `roman`/`function` field exists.
Everything in `cut-points-and-cadences.md` (classifying a chord as tonic/predominant/
dominant) is inferred by you, per request, from the raw root against the song's
`MusicMap.key` — not looked up. Treat it as judgment, not a verified fact from the map.

## No cadence detection in the map

`EnrichedSegment` has no `cadences` field at all. The entire cadence-quality workflow
in `cut-points-and-cadences.md` — classifying a boundary as a Perfect Authentic
Cadence vs. a half cadence vs. an elision — is manual pattern-matching against
`chords` entries, not a pre-computed, validated signal. Two reasonable readings of
ambiguous chord data can disagree; say so rather than presenting a classification as
certain.

## No sub-phrase repeat detection

`EnrichedSegment.phrases` is timestamps only — nothing marks "this phrase is a literal
repeat of the previous one." Shared with the `cutting` skill's known-limitations.md.
Relevant here for `phrase-boundaries-and-groove.md`: identifying a repeated phrase for
loop-point selection is still a judgment call between `phrases` entries, not a lookup.

## No per-instrument/vocal activity signal

Same root cause as `cutting` skill's "No per-instrument/stem editing" — the map
describes the full mix, `loudness_db`/`_start`/`_end` is the only quantitative density
signal. Directly affects two things this skill reasons about:
- `hooks-and-highlights.md`'s vocal-entry identification — inferred from loudness
  shape, not a vocal-presence signal.
- Exit/outro section selection: a segment with **fewer instruments** (esp. drums)
  tends to fade/end more naturally, but the map has no way to tell "quiet because
  sparse" from "quiet but still has drums." Found in practice (2026-09-01,
  `summer-party` ambient soundscape work) — `../../cutting/references/exit-design.md`'s
  energy-based ranking doesn't factor in instrumentation, only loudness.

## Chord/segment timestamps aren't perfectly aligned

Chords and structural segments come from different models (`src/recut/map/helpers.py`,
`chords_in()`'s `min_overlap` parameter exists specifically because "chords and
segments come from different models, so timestamps can be slightly mismatched"). A
chord entry a few hundred ms either side of a segment boundary may belong
conceptually to the neighboring section even though its timestamp says otherwise —
worth a sanity check before trusting a cadence classification right at a boundary.

## No map generation or edit-mechanics concerns here

This skill doesn't build/enrich a `MusicMap` (`recut analyze`/`recut map`,
`src/recut/map/make_map.py`) or touch `Clip`/`XFade`/`compose()` itself — see
`SKILL.md`. Map-generation-side limitations (analysis timeouts, model licensing) are
in the repo-root `LIMITATIONS.md`, not duplicated here.
