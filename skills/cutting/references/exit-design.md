# Exit Design

*Two exit-design docs: this one is the recipes (which `plan.json` fields build an exit). For the musical judgment of where an exit works (pace, loudness, key), read `skills/music-theory/references/exit-design.md`. Use that to pick the place, this to build the exit.*

How to end a cut deliberately. The exit is the listener's last impression — it should feel intentional, not truncated.

## Choosing the exit point

Always land on a downbeat — never end mid-bar. Segment boundaries are already
downbeat-snapped at map-generation time (see `map-interpretation.md`), so a clip with no
`bars`/`beats` naturally ends on one; use an explicit `bars`/`beats` length
when ending mid-segment instead.

**Best exit zones, in order of preference:**
1. End of a `chorus` — highest emotional resolution.
2. End of an `outro`/`ending` — the listener already expects closure there.
3. End of a repeated `phrases` entry — the repetition itself signals "this is ending."
4. Mid-section only if there's a natural breath (a held chord, a break) visible in `loudness_db`.

This ranking is where the section ends; the music-theory doc adds the density check at that spot: the exit should land where `pace` is already falling. If the end of a chorus is still busy (pace 0.7 or higher), prefer the ending transplant or a longer fade, or exit at a quieter earlier edge, rather than fading a busy groove.

Bar-align the cut first, then design the exit working backwards from it.

## Match the ending to the request first

Before picking a type, decide what *kind* of ending the request wants. Evidence: ticket
20261118-idzo spent 4 rejected iterations on the song's real finale ("something more natural
... now the ending is using some loud strings, not really what we want ... ideally
harmonically cohesive") before the operator suggested a single chord hit.

- **Read the character words.** "natural", "soft", "fade", "calm" vs "big finish", "ff",
  "strong". If the client is unsure, make one of each as separate iterations and say in
  `plan.notes` which is which.
- **Measure the candidate ending against the bars before the cut** (`loudness_short_term`,
  `pace_at`, the `other`/`drum` activity). A song's real ending is often its loudest, busiest
  part (full strings, a finale): 6 dB louder or clearly busier than what precedes it is a big
  finish, not a natural one. Don't transplant it for a "natural" request.
- **Harmonically cohesive:** the ending's first chord continues from the chord at the cut (the
  same chord, or a V → I into it); read `chords` on both sides.
- **Nothing heard just before:** don't reuse material the listener heard in the last minute.

## Exit types

**First check whether the song's own ending is what you want.** The most common manual fix is to take the ending from the end of the song and place it where the cut ends (a shortened version that still closes properly). That is the **ending transplant**: `ending-transplant.md` has three variants as `plan.json` snippets (hit on top with the old tail ringing, a reverb wash into the ending, or a normal crossfade with shared reverb). Use it before building a synthetic fade.

### 1. Hard edit
Fade out over the last few bars of the final clip. Clean, fast, and often correct — don't reach for something more elaborate unless asked.

```json
{"id": "n9", "type": "clip", "source": "a", "segment": "outro", "index": 1,
 "fade_out": {"length": "2 bars", "shape": "equal_power"}}
```

### 2. Density fade-out
Since effects apply to the whole mix (no live per-instrument removal — see `known-limitations.md`), a "things drop away" feeling comes from the LAST 2–3 clips of the sequence at progressively lower level and brightness, not from literally muting one instrument at a time:

```json
{"id": "n7", "type": "clip", "source": "a", "segment": "outro", "index": 1, "gain": -1.5},
{"id": "n8", "type": "clip", "source": "a", "segment": "outro", "index": 2,
 "devices": [{"id": "f1", "type": "auto_filter", "filter": "lowpass", "frequency": 18000}],
 "automation": [{"target": "devices.f1.frequency", "from": 18000, "to": 6000, "over": "2 bars", "shape": "exp"}]},
{"id": "n9", "type": "clip", "source": "a", "segment": "outro", "index": 3, "sends": {"A": -6},
 "devices": [{"id": "f2", "type": "auto_filter", "filter": "lowpass", "frequency": 6000}],
 "automation": [{"target": "devices.f2.frequency", "from": 6000, "to": 200, "over": "2 bars", "shape": "exp"}],
 "fade_out": {"length": "2 bars", "shape": "exp"}}
```

(with a reverb return `A` in `returns`). Use when the brief explicitly asks for something that winds down over time, not for a fast/clean edit.

### 3. Filter-sweep exit
A lowpass `auto_filter` sweep plus a send to a reverb return, ending in a `fade_out` — "dissolving into space."

```json
{"id": "n9", "type": "clip", "source": "a", "segment": "ending", "index": 1, "sends": {"A": -4},
 "devices": [{"id": "flt", "type": "auto_filter", "filter": "lowpass", "frequency": 8000}],
 "automation": [{"target": "devices.flt.frequency", "from": 8000, "to": 200, "over": "4 bars", "shape": "exp"}],
 "fade_out": {"length": "1 bar", "shape": "exp"}}
```

The reverb return keeps ringing after the fade, so the last chord dissolves rather than stops. Fade only the **last ~25%** of the section — the listener needs to hear the final chord before it goes.

### 4. Final chord hit (button)
End on **one attack** of a chord the song already plays (the chord at the cut or its tonic),
and let a reverb return carry the ring. Natural, short, harmonically cohesive; works when the
song has no quiet ending of its own.

```json
{"id": "hit", "type": "clip", "source": "a", "segment": "inst", "index": 1, "beats": 1,
 "fade_out": {"length": "30ms", "shape": "linear"}, "sends": {"A": -24},
 "automation": [{"target": "sends.A", "from": -24, "to": -10, "over": "2 beats", "at": "start"}]}
```

- **The hit is alone.** It ends before the next note of *any* instrument (a string
  subdivision, a hi-hat) starts: check the onsets after the attack and shorten `beats`.
  The 30 ms `fade_out` only covers the click; the return does the ringing.
- **Reverb bloom:** return as in `ending-transplant.md` (low cut, decay 3-6 s for a final
  chord). Send peak -9 to -13 dB on a loud master; on a sparse or quiet source up to about
  -4 dB (ticket 20261118-fzsv: a -12 dB peak left the tail 15 dB under the dry chord and it
  read as a dry stop; -4 dB over the last 8 beats was approved).
- **A drum hit on top** (kick or crash from the drum stem) goes on its own track, placed with
  a leading `gap`. Align its **impact** (the loudest point of the hit) with the chord's attack,
  not the clip start and not the onset of a roll before it: 150 ms late was heard at once
  (20261118-idzo). Find the impact in the stem's waveform, then listen.
- **Switching to a stem for the last note** (e.g. strings only, to drop the band) removes
  everything else at that moment: keep the stems you still want (the drum stem) on layer
  tracks across the switch, or the switch itself is heard as a cut.
- **Hit too quiet against the drums?** Layer a second attack of the same chord from elsewhere
  in the song (`other` stem) instead of raising gain into the limiter.

## Fade timing

**Common mistake:** starting the fade too early. Cover no more than the last 4 bars (or last 25% of the exit section) — if the exit section is 20s, the fade starts around 15s, not at 0.

## Quick reference — symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| Audible "room switch" at exit start | `auto_filter` started at an audible cutoff | Start near the edge of the audible range, and use `shape: "exp"` |
| Click at a transition | Level/effect changed all at once | Stagger changes across the last few clips (`transitions-and-masking.md`), or lengthen the `xfade` |
| Exit feels truncated | Fade started too early | Fade last ~25% only |
| Bloom at the end | `reverb` stacked on already-reverberant content | One reverb return only; don't also insert one on the clip |
