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

**The reverb return** used below. The recipe is general (any return reverb on a loud master):

- `eq` `low_cut` 200 to 300 Hz **before** the reverb. Kick and bass in the reverb are the
  main cause of a squashed ending: the long low-end tail adds a lot of energy to the mix
  and pumps the master limiter.
- Moderate `decay`: 1.5 to 2.5 s for a wash into an ending (3 to 4 s only on a quiet or sparse
  source). `size` 50 to 60, `hi_cut` 4500 to 6000, `pre_delay` 20 to 30 ms.
- Send **peak** around -9 to -13 dB. Never 0 dB on a `dry_wet: 100` return: that is as loud as
  the dry signal and the limiter pays for it.
- Never ramp from `"-inf"`. A send that starts from true silence and climbs fast is
  audible as the reverb "switching on". Start from a low base level (-24 to -30 dB, set as
  the static send so it also covers the whole clip) and ramp up over **2 beats or more**.

```json
{"id": "A", "name": "Reverb", "devices": [
  {"id": "lc", "type": "eq", "low_cut": 250},
  {"id": "verb", "type": "reverb", "decay": "2s", "pre_delay": "30ms",
   "size": 60, "hi_cut": 4500, "dry_wet": 100}]}
```

`dry_wet` stays at 100 on a return: the dry signal goes to the mix on its own, and the
send level decides how much reverb you hear.

Evidence behind these numbers (ticket 20261113-mbyv, a loud mastered EDM track): the first
wash (send ramped from -inf to 0 dB over 1 beat, 3.5 s decay, no low cut) was rejected as
"reverb squash" with 3.4 dB of limiting (`fx_wrong`). The second session's try (low cut 250 Hz,
2 s, send to -9 dB over 2 beats) cleared `qc_limiting` and was "much better, still I feel the
reverb gets turned on"; a send starting at -26 dB and rising to -13 dB was "okay for now".

## Variant 1: hit on top, tail rings

The outgoing clip opens its send on the last bar, so the reverb is already full when the
join happens. The join is a **short** `xfade` whose incoming side is `hold`: the ending is
at full level from its first sample, and the old part is gone from the dry signal almost
at once. Only the reverb carries on, under the hit.

```json
{
  "returns": [
    {"id": "A", "name": "Reverb", "devices": [
      {"id": "lc", "type": "eq", "low_cut": 250},
      {"id": "verb", "type": "reverb", "decay": "2s", "pre_delay": "30ms",
       "size": 60, "hi_cut": 4500, "dry_wet": 100}]}
  ],
  "tracks": [{"id": "main", "clips": [
    {"id": "n1", "type": "clip", "source": "a", "segment": "intro", "index": 1},
    {"id": "n2", "type": "clip", "source": "a", "segment": "chorus", "index": 1, "bars": 4,
     "sends": {"A": -26},
     "automation": [{"target": "sends.A", "from": -26, "to": -9, "over": "2 beats",
                     "at": "end", "shape": "linear"}]},
    {"id": "x1", "type": "xfade", "length": "30ms", "out_shape": "equal_power", "in_shape": "hold"},
    {"id": "n3", "type": "clip", "source": "a", "segment": "inst", "index": 1, "offset_bars": 4}
  ]}]
}
```

Listen for: the hit should feel like it lands *into* a room, not a jump cut. If the old
part's reverb is too loud under the hit, lower the send `to` (try `-13`); if the splice
clicks, lengthen the `xfade` to `"60ms"`.

## Variant 2: reverb wash into the ending

The send ramps up over the **last 2 beats or more** of the outgoing clip (`at: "end"`
means the ramp finishes exactly at the clip's end), so the final beats smear into the
wash. The join is the same 30 ms `hold`-out/`equal_power`-in blend: the outgoing dry
signal stays at full level until the ending arrives, and the wash rings on.

```json
{
  "returns": [
    {"id": "A", "name": "Reverb", "devices": [
      {"id": "lc", "type": "eq", "low_cut": 250},
      {"id": "verb", "type": "reverb", "decay": "2s", "pre_delay": "30ms",
       "size": 60, "hi_cut": 4500, "dry_wet": 100}]}
  ],
  "tracks": [{"id": "main", "clips": [
    {"id": "n1", "type": "clip", "source": "a", "segment": "verse", "index": 1},
    {"id": "n2", "type": "clip", "source": "a", "segment": "chorus", "index": 1, "bars": 4,
     "sends": {"A": -28},
     "automation": [{"target": "sends.A", "from": -28, "to": -12, "over": "2 beats",
                     "at": "end", "shape": "linear"}]},
    {"id": "x1", "type": "xfade", "length": "30ms", "out_shape": "hold", "in_shape": "equal_power"},
    {"id": "n3", "type": "clip", "source": "a", "segment": "inst", "index": 1, "offset_bars": 4,
     "fade_out": {"length": "2 bars", "shape": "exp"}}
  ]}]
}
```

The send starts from a low base (-28 dB), not from silence, and peaks at -12 dB: the reverb
is already faintly there, so it never "switches on". `linear` is the safe shape; `exp` hides
the start of the ramp but makes its end steeper, so use it only with a base that is already low
(-30 dB) and `"over": "1 bar"` or more. (`examples/summer-party/plans/02-ending-transplant.json`
is an older plan that predates this recipe.)

Listen for: a swell that peaks right at the join and no moment where the reverb "turns
on". If you can hear it start, lower the base (-30) or lengthen `over`; if the ending
sounds dry after it, raise the peak to -6 (not higher) or the `decay` to 2.5 s.

## Variant 3: normal crossfade + reverb on a return

A regular blend. Both clips send a little to the return, so the two parts share the same
space during the overlap, and the ending's own tail rings out after the very last note.

```json
{
  "returns": [
    {"id": "A", "name": "Reverb", "devices": [
      {"id": "lc", "type": "eq", "low_cut": 250},
      {"id": "verb", "type": "reverb", "decay": "2s", "pre_delay": "20ms",
       "size": 60, "hi_cut": 5500, "dry_wet": 100}]}
  ],
  "tracks": [{"id": "main", "clips": [
    {"id": "n1", "type": "clip", "source": "a", "segment": "chorus", "index": 1, "bars": 4,
     "sends": {"A": -15}},
    {"id": "x1", "type": "xfade", "length": "2 beats", "shape": "equal_power"},
    {"id": "n2", "type": "clip", "source": "a", "segment": "inst", "index": 1, "offset_bars": 4,
     "sends": {"A": -12}}
  ]}]
}
```

Listen for: the join disappearing into one space. If the blend sounds muddy, shorten the
xfade or lower the sends; for a drier ending, remove the `sends` on `n2`.

## Checks before you ship it

- `recut ticket render <id>` and read the issues. The overlap and the reverb add up, and the
  master limiter (on by default at -1 dB) brings the mix back. A `qc_limiting` warning means
  the limiter pulled the level down by more than 3 dB somewhere (audible squash): first check the
  return has the `eq` `low_cut` above, then lower the send peak by 3 dB or the clip `gain`
  by 2 to 3 dB.
- `qc_loudness` compares the render with the sources it uses (warns if it is more than 1 LU louder
  than the loudest one, or more than 3 LU quieter than them), so a loud master is not flagged by
  itself: if it fires, the cut really got louder or quieter. The master limiter also holds the
  true peak (not just the sample peak) at the ceiling, so `qc_true_peak` should stay silent.
- `returns_tail_end` in `render.json` is when the reverb dies out. If it is far past the last
  clip, the final tail is longer than you want: shorten `decay`.
- The validator's "cut starts at ..." / "ends abruptly" notes are about the cut's first and
  last clips, not about the transplant. Start with the intro or add a `fade_in`, and end
  the cut on the ending clip.
- Tempo and key: the ending belongs to the same song, so both are right by construction. If
  you transplant an ending from another source, the cross-song rules (`downbeat`, `bpm_gap`,
  `key_compat`) apply.
