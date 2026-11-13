# Ending Transplant

The most common manual fix: the song's **real ending** (its last bars) is placed mid-song,
so a shortened cut still closes the way the artist intended. Three variants, from tightest
to smoothest. Pick by what the join needs (see the table), render, and listen.

| Variant | Use when | Sounds like |
|---|---|---|
| 1. Hit on top + tail rings | the cut section ends on a held chord or a strong downbeat, and the ending starts with a hit | the ending slams in while the old part's reverb rings under it |
| 2. Reverb wash into the ending | the cut section is dense or rhythmic and a straight cut would feel abrupt | the last beat or two dissolve into a wash, the ending lands out of it |
| 3. Normal crossfade + reverb | the two parts are close in energy and key | a regular blend, with a bit of shared space so it doesn't sound pasted |

All three use the same pieces: a **return track** (`A`, a reverb), `sends` on the clips that
feed it, and an `xfade` join. Returns keep ringing after the clips that feed them end, so
tails are never cut off; there is no special "ring out" field.

**Choosing the ending.** It is the last N bars of the last section: `segment: "outro"` if the
map has one, otherwise the last section with `offset_bars` (the section's bar count minus 4).
Check the clip's length with `recut ticket render` (the splice list shows each segment's
source times). The ending has to start on a downbeat; `offset_bars` always does.

**The reverb return** used below (`decay` 3.5 s is long enough to hear, short enough not to
smear the ending; `hi_cut` keeps the tail from getting harsh):

```json
{"id": "A", "name": "Reverb", "devices": [
  {"id": "verb", "type": "reverb", "decay": "3.5s", "pre_delay": "20ms",
   "size": 80, "hi_cut": 6000, "dry_wet": 100}]}
```

`dry_wet` stays at 100 on a return: the dry signal goes to the mix on its own, and the
send level decides how much reverb you hear.

## Variant 1: hit on top, tail rings

The outgoing clip opens its send on the last bar, so the reverb is already full when the
join happens. The join is a **short** `xfade` whose incoming side is `hold`: the ending is
at full level from its first sample, and the old part is gone from the dry signal almost
at once. Only the reverb carries on, under the hit.

```json
{
  "returns": [
    {"id": "A", "name": "Reverb", "devices": [
      {"id": "verb", "type": "reverb", "decay": "3.5s", "pre_delay": "20ms",
       "size": 80, "hi_cut": 6000, "dry_wet": 100}]}
  ],
  "tracks": [{"id": "main", "clips": [
    {"id": "n1", "type": "clip", "source": "a", "segment": "intro", "index": 1},
    {"id": "n2", "type": "clip", "source": "a", "segment": "chorus", "index": 1, "bars": 4,
     "sends": {"A": "-inf"},
     "automation": [{"target": "sends.A", "from": "-inf", "to": -6, "over": "1/4",
                     "at": "3 bars", "shape": "linear"}]},
    {"id": "x1", "type": "xfade", "length": "30ms", "out_shape": "equal_power", "in_shape": "hold"},
    {"id": "n3", "type": "clip", "source": "a", "segment": "inst", "index": 1, "offset_bars": 4}
  ]}]
}
```

Listen for: the hit should feel like it lands *into* a room, not a jump cut. If the old
part's reverb is too loud under the hit, lower the send `to` (try `-10`); if the splice
clicks, lengthen the `xfade` to `"60ms"`.

## Variant 2: reverb wash into the ending

The send ramps open over the **last 1 or 2 beats** of the outgoing clip (`at: "end"`
means the ramp finishes exactly at the clip's end), so the final beats smear into the
wash. The join is the same 30 ms `hold`-out/`equal_power`-in blend: the outgoing dry
signal stays at full level until the ending arrives, and the wash rings on.

```json
{
  "returns": [
    {"id": "A", "name": "Reverb", "devices": [
      {"id": "verb", "type": "reverb", "decay": "3.5s", "pre_delay": "20ms",
       "size": 80, "hi_cut": 6000, "dry_wet": 100}]}
  ],
  "tracks": [{"id": "main", "clips": [
    {"id": "n1", "type": "clip", "source": "a", "segment": "verse", "index": 1},
    {"id": "n2", "type": "clip", "source": "a", "segment": "chorus", "index": 1, "bars": 4,
     "sends": {"A": "-inf"},
     "automation": [{"target": "sends.A", "from": "-inf", "to": 0, "over": "1 beat",
                     "at": "end", "shape": "exp"}]},
    {"id": "x1", "type": "xfade", "length": "30ms", "out_shape": "hold", "in_shape": "equal_power"},
    {"id": "n3", "type": "clip", "source": "a", "segment": "inst", "index": 1, "offset_bars": 4,
     "fade_out": {"length": "2 bars", "shape": "exp"}}
  ]}]
}
```

`shape: "exp"` keeps the send almost closed until the very end of the ramp, then swells:
the wash blooms on the last beat instead of fading in from the start of it. Use `"over": "2 beats"`
for a longer build, or `"linear"` if the exp swell is too sudden. This is the plan in
`examples/summer-party/plans/02-ending-transplant.json`.

Listen for: a swell that peaks right at the join. If the wash is audible well before the
last beat, shorten `over`; if the ending sounds dry after it, raise the reverb return's
`decay`.

## Variant 3: normal crossfade + reverb on a return

A regular blend. Both clips send a little to the return, so the two parts share the same
space during the overlap, and the ending's own tail rings out after the very last note.

```json
{
  "returns": [
    {"id": "A", "name": "Reverb", "devices": [
      {"id": "verb", "type": "reverb", "decay": "2.5s", "pre_delay": "10ms",
       "size": 60, "hi_cut": 7000, "dry_wet": 100}]}
  ],
  "tracks": [{"id": "main", "clips": [
    {"id": "n1", "type": "clip", "source": "a", "segment": "chorus", "index": 1, "bars": 4,
     "sends": {"A": -12}},
    {"id": "x1", "type": "xfade", "length": "2 beats", "shape": "equal_power"},
    {"id": "n2", "type": "clip", "source": "a", "segment": "inst", "index": 1, "offset_bars": 4,
     "sends": {"A": -9}}
  ]}]
}
```

Listen for: the join disappearing into one space. If the blend sounds muddy, shorten the
xfade or lower the sends; for a drier ending, remove the `sends` on `n2`.

## Checks before you ship it

- `recut ticket render <id>` and read the issues. The overlap and the reverb add up, and the
  master limiter (on by default at -1 dB) brings the mix back. A `qc_limiting` warning means
  the limiter pulled the level down by more than 3 dB somewhere (audible squash): lower a send
  by 3 dB or the clip `gain` by 2 to 3 dB, or the ending will sound squashed.
- `returns_tail_end` in `render.json` is when the reverb dies out. If it is far past the last
  clip, the final tail is longer than you want: shorten `decay`.
- The validator's "cut starts at ..." / "ends abruptly" notes are about the cut's first and
  last clips, not about the transplant. Start with the intro or add a `fade_in`, and end
  the cut on the ending clip.
- Tempo and key: the ending belongs to the same song, so both are right by construction. If
  you transplant an ending from another source, the cross-song rules (`downbeat`, `bpm_gap`,
  `key_compat`) apply.
