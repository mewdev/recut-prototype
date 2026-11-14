# Exit and join design with pace

*Judgment doc: it says where an exit or join works, using the map's pace, loudness and key. The recipes that build the exit (fade-out, filter sweep, ending transplant as `plan.json` snippets) are in `skills/cutting/references/exit-design.md`; its "best exit zones" ranking (end of a chorus, then outro) is the section choice, and the pace rules below refine it.*

The map's `pace` series (onset events per minute, `normalized` 0-1 per track, one sample per
second) and `loudness_short_term` (LUFS) tell you how busy a place is, independent of BPM.
Read them with `recut.map.helpers.pace_at(map, t)`; each section also has a mean `pace`.
Maps made before pace existed have none: run `recut ticket enrich <id>`. Instrument activity
(drums, vocals) is not available yet, so pace is the only density signal; loudness alone
cannot tell "quiet but busy" from "sparse".

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
