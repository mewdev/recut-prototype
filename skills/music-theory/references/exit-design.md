# Exit and join design with pace

*Judgment doc: it says where an exit or join works, using the map's pace, loudness and key. The recipes that build the exit (fade-out, filter sweep, ending transplant as `plan.json` snippets) are in `skills/cutting/references/exit-design.md`; its "best exit zones" ranking (end of a chorus, then outro) is the section choice, and the pace rules below refine it.*

The map's `pace` series (onset events per minute, `normalized` 0-1 per track, one sample per
second) and `loudness_short_term` (LUFS) tell you how busy a place is, independent of BPM.
Read them with `recut.map.helpers.pace_at(map, t)`; each section also has a mean `pace`.
Maps made before pace existed have none: run `recut ticket enrich <id>`. Loudness alone
cannot tell "quiet but busy" from "sparse": for that use the instrument activity below.

- **Character before place.** First decide what kind of ending the request wants (natural /
  soft vs. big finish) and measure the candidate ending against the bars before the cut: a
  song's real finale is often its loudest part and is wrong for a "natural" request. Recipes,
  including the final chord hit: `skills/cutting/references/exit-design.md`.
- **Exit on a falling pace.** A clean ending usually comes where pace is already dropping
  (about 0.3 or lower, for a few seconds). A fade over a section still at pace 0.7 or higher
  cuts a busy groove: the fade sounds like the song being switched off.
- **Joins: match pace, not loudness.** An xfade between a pace-0.8 exit and a pace-0.2
  entry feels like a drop even when the LUFS match. Bridge it with a longer overlap, or
  pick an entry nearer in pace.
- **Rises are cut points too.** A build (pace climbing over 4-8 bars) should be taken whole
  or not at all: land the cut on the pace peak, not in the middle of the climb.
- **A high-BPM breakdown is low pace.** Judge energy by `pace`, not `bpm`.
- **Key.** `key_at(map, t)` gives the key in force at `t`; a key change inside a clip is a
  reason to splice at its edge (`map.key_ranges`).

## Instrument activity: drums and vocals

When the map has `instrument_activity` (Demucs stems; `analysis_sources.instrument_activity`;
older maps: `recut ticket enrich <id>`), `drum`, `bass`, `vocal` and `other` are 0-1 curves (0.1 s
steps, each stem scaled to its own loud level) with `ranges` where the stem is clearly playing for
at least a bar. Read them with `recut.map.activity.activity_at(map, "drum", t)`; sections carry
`drum_activity` and `vocal_activity` means.
- **Never fade a groove.** A `fade_out` over a section whose last-bar drum activity is above
  about 0.6 sounds like switching the song off (the linter warns: `ending_drums`). Exit on a drum
  break or a section edge, or end on the chord with a short tail, instead. "Quiet but still
  has drums" is a high drum activity at low loudness: it reads as a groove, not as an ending.
- **Don't cut a sung phrase in half.** A splice more than one beat inside a vocal range
  cuts a line mid-word (the linter warns: `mid_vocal`). Move it to the range's edge (the end
  of the line, a breath), or to a bar where `vocal` is near 0.
- **Joins:** the best entry has the outgoing and incoming drum activity close; entering a vocal
  over a vocal in the outgoing track is a clash unless one of them is pushed down.
