# Exit Design

How to end a cut deliberately. The exit is the listener's last impression — it should feel intentional, not truncated.

## Choosing the exit point

Always land on a downbeat — never end mid-bar. Segment boundaries are already
downbeat-snapped at map-generation time (see `map-interpretation.md`), so a bare
`Clip(segment_name)` naturally ends on one; use an explicit `bars`/`beats` boundary
when ending mid-segment instead.

**Best exit zones, in order of preference:**
1. End of a `chorus` — highest emotional resolution.
2. End of an `outro`/`ending` — the listener already expects closure there.
3. End of a repeated `phrases` entry — the repetition itself signals "this is ending."
4. Mid-section only if there's a natural breath (a held chord, a break) visible in `loudness_db`.

Bar-align the cut first, then design the exit working backwards from it.

## Exit types

### 1. Hard edit
Fade out over the last few bars of the final `Clip`. Clean, fast, and often correct — don't reach for something more elaborate unless asked.

```python
Clip("outro", fx=[Fade(vol_start=1.0, vol_end=0.0, curve="qsin")])
```

### 2. Density fade-out
Since effects apply to the whole mix (no live per-instrument removal — see `known-limitations.md`), a "things drop away" feeling comes from chaining the LAST 2–3 `Clip`s of the sequence at progressively lower loudness/effect intensity, not from literally muting one instrument at a time:

```python
Clip("outro", index=1, fx=[Fade(vol_start=1.0, vol_end=0.85)]),
Clip("outro", index=2, fx=[FilterSweep(filter_type="low", freq_start=18000, freq_end=6000, curve=2.5)]),
Clip("outro", index=3, fx=[FilterSweep(freq_start=6000, freq_end=200, curve=2.5), Reverb(wetness=0.4, reverb_type="hall"), Fade(vol_start=1.0, vol_end=0.0)]),
```

Use when the brief explicitly asks for something that winds down over time, not for a fast/clean edit.

### 3. Filter-sweep exit
`FilterSweep(filter_type="low", ...)` combined with `Reverb`, ending in a `Fade` — "dissolving into space."

```python
Clip("ending", fx=[
    FilterSweep(filter_type="low", freq_start=8000, freq_end=200, curve=2.5),
    Reverb(wetness=0.4, reverb_type="hall"),
    Fade(vol_start=1.0, vol_end=0.0),
])
```

Fade only the **last ~25%** of the section — the listener needs to hear the final chord before it goes.

## Fade timing

**Common mistake:** starting the fade too early. Cover no more than the last 4 bars (or last 25% of the exit section) — if the exit section is 20s, the fade starts around 15s, not at 0.

## Quick reference — symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| Audible "room switch" at exit start | `FilterSweep` started at an audible cutoff | Start near the edge of the audible range, or `curve > 1` |
| Click at a transition | Level/effect changed all at once | Stagger changes across the last few `Clip`s (`transitions-and-masking.md`) |
| Exit feels truncated | Fade started too early | Fade last ~25% only |
| Bloom at the end | `Reverb` stacked on already-reverberant content | Don't chain two `Reverb`s; use one, later in the chain |
