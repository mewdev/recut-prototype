# Chicago — Edit Plan v7

## Changes from v6

### 1. Drums EQ — push cutoff to 400Hz
- v6 cut at 120Hz: removed kick fundamental (60–100Hz) but left the body (100–300Hz)
- 100–300Hz is where the reverb bloom lives — punch and thump still accumulated
- 400Hz removes everything below upper-mids: only snare crack, hi-hat, cymbal shimmer survives
- Result: reverb only captures percussive transients, no tonal/bass content to bloom

### 2. Drums reverb wetness — 1.0 → 0.7
- 100% wet at wide hall = very long tail, adds spaciousness but can feel disconnected
- 0.7 wet blends it into the mix more naturally while still reading as "ambient"

### 3. End section (2:29 / sweep_rel) — piano-only, no double reverb
- v5/v6 bug: `sweep_seg = mix[:, sweep_samp:]` included `drums_rev` (already reverbed)
  → filter_sweep + reverb applied on top of reverb = double bloom, murky end
- Fix: taper `drums_rev` out at sweep_samp (same 0.3s taper)
  Then apply creative chain to piano-only slice from sweep_samp
  Piano is continuous — no split/join needed, just operate on `piano[:, sweep_samp:]`

---

## Insight: why v5/v6 end got worse than v4

v4 had a bug (xfade_join timing) but the creative exit was built from `piano_b_sweep`
— a pure piano slice. filter_sweep + reverb on clean piano = controlled, musical.

v5 "fixed" the timing by using the full mix for the sweep section. But that pulled
`drums_rev` into the chain. reverb(reverb(drums)) = exponentially longer tail,
undefined phase, washed-out mud. The timing fix introduced a signal-path regression.

v7 keeps the v5 additive-mix architecture (correct timing) but terminates `drums_rev`
at the sweep boundary, so the creative exit is piano-only — same signal path as v4's
good-sounding end, with v5's correct timing.

---

## Lessons learned (cumulative)

1. Kick + reverb = bass mud — high-pass drums before reverb (now at 400Hz, not 120Hz)
2. When fixing one bug, trace the full signal path — v5 timing fix broke the end chain
3. Reverbed stems should not enter a second reverb chain — terminate them at section boundaries
4. 100% wet + wide hall = disconnected; 0.65–0.75 blends more naturally
5. Never xfade_join time-aligned stems — additive mixing on single timeline

---

## Signal path summary

| Region | piano | bass | vox | drums_dry | drums_rev |
|--------|-------|------|-----|-----------|-----------|
| 0 → cut_rel (2:15) | full | full | full | full | silent |
| cut_rel → sweep_rel (2:15–2:29) | full | silent | silent | silent | eq(400Hz,high)→reverb(0.7,hall) |
| sweep_rel → end (2:29+) | filter_sweep→reverb→fade | silent | silent | silent | **tapered out** |

## Key timestamps (unchanged)
| Event | Clip | Original |
|-------|------|---------|
| Start | 0:00 | 1:01.56 (61.56s) |
| Outro phrase A | 2:01 | 3:02.56 (182.56s) |
| Phrase A repeat — reverb drums | 2:15 | 3:16.68 (196.68s) |
| Chorus — piano creative exit | 2:29 | 3:30.90 (210.90s) |
| End | ~2:49 | ~3:51 (231s) |

## Output
- `testing/02/chicago-cut-v7.mp3`
