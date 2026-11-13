# Exit Design

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

Bar-align the cut first, then design the exit working backwards from it.

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

## Fade timing

**Common mistake:** starting the fade too early. Cover no more than the last 4 bars (or last 25% of the exit section) — if the exit section is 20s, the fade starts around 15s, not at 0.

## Quick reference — symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| Audible "room switch" at exit start | `auto_filter` started at an audible cutoff | Start near the edge of the audible range, and use `shape: "exp"` |
| Click at a transition | Level/effect changed all at once | Stagger changes across the last few clips (`transitions-and-masking.md`), or lengthen the `xfade` |
| Exit feels truncated | Fade started too early | Fade last ~25% only |
| Bloom at the end | `reverb` stacked on already-reverberant content | One reverb return only; don't also insert one on the clip |
