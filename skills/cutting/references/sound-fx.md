# Sound FX between songs (voice hits, screams, stingers)

Requests like "hell intro, then a scary sound effect, a pause, then the song" or "use the
voice effects from song B as a transition". The FX is usually a short (1–3 s) vocal shout,
scream or spoken phrase taken from one of the client's own tracks.

## 1. You cannot hear: let the operator pick, once

Audio features (loudness, spectral centroid, activity curves) find *candidates*, not the right
sound. Picking a "scream" from features alone was wrong on ticket 20261118-jn7o and cost two
review rounds. Before writing the FX into the plan:

1. `recut ticket audition <id> <source>` writes every short (≤ 4 s, `--max-s`) phrase of the
   source's `vocal` activity (`--stem drum|bass|other` for others) as a padded WAV into
   `<session>/audition/`, cut from the separated stem when it was kept. The filename is the
   source time, e.g. `a_vocal_13.3-14.9.wav`.
2. If it says the map has no activity (ticket analyzed before stems were kept): `recut ticket enrich <id> --force`.
3. Ask the operator **one** question: "Which of these (by filename) is the FX? Several can be
   combined." Then build the plan from the answer.

If the operator already gave timestamps, skip the audition. Timestamps quoted from a *rendered*
iteration are in the edit's timeline: map them back to source time with the iteration's
`render.json` (`segments[].out_start` and the clip's source start).

## 2. Clean voice: use the stem as a source

A voice hit with drums and music under it rarely works as an FX. Use the separated stem: it
has the song's timeline, so add it as a source with the song's map and cut it like the song:

```json
"sources": {
  "a": {"file": "inputs/a.mp3", "map": "maps/a.json"},
  "a_vox": {"file": "stems/a/vocals.flac", "map": "maps/a.json"}
}
```

Any stem works the same way (`drums.flac`, `bass.flac`, `other.flac`): a drum fill or a
synth stab is an FX too. Stems are kept by default; if `stems/<source>/` is missing (older
ticket): `recut ticket enrich <id> --force`. A stem gets the same loudness-matching
gain as its own mix, so it keeps its natural level against the song.

A phrase rarely starts on a beat: pick it with fractional `offset_beats` / `beats` from the
`vocal` range (offsets count from the section's first downbeat).

## 3. Stacking: one layer per phrase

Phrases that sound at the same time go on separate tracks. Each FX track starts with a `gap`
that places it on the timeline (the time in the output where the FX should enter):

```json
"tracks": [
  {"id": "main", "clips": [ ...song A..., {"id": "p1", "type": "gap", "length": "8s"}, ...song B... ]},
  {"id": "fx1", "clips": [{"id": "g1", "type": "gap", "length": "19.55s"},
    {"id": "v1", "type": "clip", "source": "a_vox", "segment": "intro", "offset_beats": 29.87, "beats": 4.62,
     "fade_in": {"length": "1.6s", "shape": "equal_power"}, "fade_out": {"length": "250ms", "shape": "exp"},
     "sends": {"A": -10}}]},
  {"id": "fx2", "clips": [{"id": "g2", "type": "gap", "length": "19.55s"}, {"id": "v2", "...": "second phrase"}]}
]
```

Read the entry time off the previous render (`render.json` segments: where song A's fade-out
starts) and set the FX gaps to it.

## 4. Placing the FX over the fade-out

"The FX starts as song A fades out" means overlap, not "after":

- Outgoing clip: `fade_out` 2 bars, `linear`. An `exp` fade-out drops to near-silence too early
  and the FX then jumps out of nothing.
- FX layer: its `gap` ends about 1.5 s before the outgoing clip ends; `fade_in` about 1.5 s,
  `equal_power`, so it rises while song A falls.
- FX clip: send to a reverb return (-12 to -10 dB) so its tail rings on into the pause.

## 5. Gluing the FX level

A layer has no splice, so the render reports its level instead: an `info` issue `layer_level`
per layer clip, e.g. `layer fx1: v1 enters at 19.55s at -12.7 LUFS, +9.0 LU against main
(-21.7 LUFS)` (first second of the layer vs the main track over the same second).

- Move the FX clip `gain` in **1–2 dB steps**, checking `layer_level` and `qc_limiting` each time.
- Reference: a voice FX entering over a linear fade-out that the operator approved as "glued"
  (ticket 20261118-jn7o) measured about **+9 LU** over the fading main track. The main track is
  falling during that second, so a large positive number is normal here.
- Operators hear 0.5–1 dB: when asked for "a bit quieter", change by that much, not more.

## 6. A pause (silence) between songs

Use a `gap` node on the main track: `{"id": "p1", "type": "gap", "length": "5s"}`. How long
the audible silence really is (tail + gap + the next song's lead-in), and what to do when no
pause was asked for: `song-sequence.md`.
