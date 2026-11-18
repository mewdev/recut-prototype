# Sound FX between songs (voice hits, screams, stingers)

Requests like "hell intro, then a scary sound effect, a pause, then the song" or "use the
voice effects from song B as a transition". The FX is usually a short (1–3 s) vocal shout,
scream or spoken phrase taken from one of the client's own tracks.

## 1. You cannot hear: let the operator pick, once

Audio features (loudness, spectral centroid, activity curves) find *candidates*, not the right
sound. Picking a "scream" from features alone was wrong on ticket 20261118-jn7o and cost two
review rounds. Before writing the FX into the plan:

1. Find candidates: phrases in the `vocal` activity ranges (`instrument_activity.vocal.ranges`
   in the map) that are short, and ideally where `drum` is not active.
2. Write 3–5 short audition files (each candidate ± 0.3 s, from the vocal stem when it exists:
   `<ticket>/stems/<source>/vocals.flac`) into the session folder, named by source time, e.g.
   `audition/a_13.3-14.9.wav`.
3. Ask the operator **one** question: "Which of these (by filename) is the FX? Several can be
   combined." Then build the plan from the answer.

If the operator already gave timestamps, skip the audition. Timestamps quoted from a *rendered*
iteration are in the edit's timeline: map them back to source time with the iteration's
`render.json` (`segments[].out_start` and the clip's source start).

## 2. Clean voice needs the stem

The plan's clips are full mixes. A voice hit with drums and music under it rarely works as an
FX. Stems are saved only with `RECUT_KEEP_STEMS=1` (`RECUT_KEEP_STEMS=1 recut ticket enrich <id>
--force`); if `stems/<source>/vocals.flac` is missing, run that first.

## 3. Stacking and stems: pre-mix the FX into its own source (workaround)

The engine renders one track and cannot read stems as plan sources (`known-limitations.md`).
Until it can, build the FX offline and add it as a source:

1. Cut each phrase from `stems/<source>/vocals.flac` with 20–30 ms edge fades, peak-normalise
   each, sum them from t = 0 (stacked = played at the same time), normalise the sum to about
   -1 dBFS, write `inputs/fx.wav` (24-bit WAV, same sample rate).
2. Map it: `tickets.ensure_maps("<id>")` (Modal) maps every input without a map; the new
   source id is the file stem (`fx`).
3. Add `"fx": {"file": "inputs/fx.wav", "map": "maps/fx.json"}` to `sources` and use it as one
   clip (its map usually has a single segment; check the name in `maps/fx.json`).

Say in `plan.notes` that the FX is a pre-mixed workaround, so the improvement pass sees it.

## 4. Placing the FX over the fade-out

"The FX starts as song A fades out" means overlap, not "after":

- Outgoing clip: `fade_out` 2 bars, `linear`. An `exp` fade-out drops to near-silence too early
  and the FX then jumps out of nothing.
- Join: `xfade` about 1.5 s, `equal_power` on both sides (it is clamped to the shorter clip).
- FX clip: send to a reverb return (-12 to -10 dB) so its tail rings on into the pause.

## 5. Gluing the FX level

The FX source is level-matched like every source, but a short dry voice measures differently
from a full mix. Use the QC numbers for the join (`qc_gain_jump` / `loudness_jump` on that
splice: LUFS before → after) and move the FX clip `gain` in **1–2 dB steps** toward a jump of
about -3 to 0 LU, checking `qc_limiting` each time. Operators hear differences of 0.5–1 dB:
when asked for "a bit quieter", change by that much, not more.

## 6. A pause (silence) between songs

There is no gap/silence clip yet (`known-limitations.md`). Use a **muted clip**: any section of
a source with `"gain": "-inf"` and a length in bars or beats that gives the pause. Return tails
keep ringing through it. `qc_gap` reports the measured near-silence; tune the length until it
matches what was asked (the FX tail eats into the start of the pause).
