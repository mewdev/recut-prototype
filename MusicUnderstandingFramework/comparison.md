 Apple MUF is a signal-first format: everything is sample-precise (44100Hz timescale), binary-encoded ML predictions, no human
  labels. Our map is semantic-first: coarse segments with named labels, chords, loudness — optimized for LLM consumption. Both
  extract similar underlying knowledge from opposite design philosophies.
  ─────────────────────────────────────────────────

  Comparison: Our Map vs Apple MUF

  ┌──────────────────┬───────────────────────────────┬────────────────────────────────────────────┐
  │    Dimension     │            Our map            │                 Apple MUF                  │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ File size        │ ~6KB                          │ 3.8MB                                      │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ Format           │ Human-readable JSON           │ Dense JSON + base64 binary                 │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ Time precision   │ Float seconds                 │ Sample-exact (÷44100)                      │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ Segment labels   │ Named (verse, chorus, bridge) │ Numeric index only                         │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ Structure levels │ 1 (segments)                  │ 3 (sections, segments, phrases)            │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ Section count    │ 10                            │ 8 sections / 16 segments / 29 phrases      │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ Beats/bars       │ Bar count per segment         │ 53 bars, 211 beats (timestamped)           │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ Chords           │ Per segment list              │ Not present                                │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ Instrument stems │ None                          │ Bass / drum / other activity timelines     │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ Loudness         │ 3 values per segment          │ Integrated / momentary / peak / short-term │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ Tempo            │ Single BPM (80.0)             │ 7 pace ranges (79.25 avg)                  │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ Key              │ None                          │ Key signature range                        │
  ├──────────────────┼───────────────────────────────┼────────────────────────────────────────────┤
  │ ML predictions   │ Labels baked in               │ Raw prediction scores (threshold 0.33)     │
  └──────────────────┴───────────────────────────────┴────────────────────────────────────────────┘

  Key gaps in our map that MUF covers:
  - Per-stem instrument activity (useful for editing decisions — e.g. cut where bass drops)
  - Phrase-level segmentation (29 phrases vs our 10 segments = finer granularity)
  - Sample-precise boundaries (our float timestamps can drift at cut points)

  What we have that MUF lacks:
  - Human-readable section labels — MUF sections are unlabeled numerically, labels are binary-encoded prediction scores
  - Chord progressions per segment — critical for harmonic edit decisions
  - Single-glance structure for LLM prompting

  The structural label count is interesting: MUF found 8 sections vs our 10 segments (including 2 silence segments). Removing
  silences, we have 8 named sections too — suggesting rough agreement on macro structure despite completely different toolchains
  (songformer vs Apple's model).

  Boundary alignment (end_of_beginning — verified in practice):
  - MUF[0–2] match our intro/verse/chorus_01 within ~0.1s ✓
  - MUF[3] merges our verse4+verse5 into one 28.5s section (same total duration, no internal split)
  - MUF[4–5] split the chorus_02→bridge boundary 3s early (109.6s vs 112.61s)
    — resolved by finding the chord change (G:maj→A:maj) + nearest downbeat in our map
  - MUF[6–7] match our chorus_03/silence ✓

  IMPORTANT: section count equality ≠ boundary equality. Always diff boundaries numerically before trusting alignment.

  Practical strategy (from session 2026-07-03):
  - Use MUF sample values for precision where boundaries align with our map (±~0.1s)
  - Use our map for section labels and as tiebreaker where models disagree
  - Use chord changes + downbeat proximity to resolve boundary conflicts
  - Best of both: MUF precision + our map semantics