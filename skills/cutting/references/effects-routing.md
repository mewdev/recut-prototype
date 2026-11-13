# Effects Routing

Which device, send or automation to reach for, and in what order. Parameters and units are in `../assets/effects-cheatsheet.md`; the plan format is `docs/PLAN.md` §3.2. Wrong routing produces resonance artifacts, mud, or an audible processing boundary.

**One track, whole mix.** The engine renders one track of full-mix clips (plus returns and master). There is no per-instrument isolation (see `known-limitations.md`). Every rule below is about what the *whole mix* will sound like.

## Inserts vs. sends

| You want | Use |
|---|---|
| A tone change on one clip (darker, thinner, quieter) | a clip **device** (`eq`, `auto_filter`, `utility`) |
| Space or echo that should ring across a join or after the end | a **send** to a **return** carrying a `reverb` or `delay` |
| A reverb or delay *on* one clip only, with its tail ringing past the clip | a clip `reverb`/`delay` **device** (the tail is kept) |
| The same effect on the whole cut | a track or master device |

Default to returns for reverb and delay: one reverb return shared by several clips sounds like one room, the dry signal is untouched, and the tail never gets cut off at a clip boundary. Don't put a full-wet reverb on a clip insert when you want space under a join.

## `auto_filter` — when and how

`filter` (`lowpass`/`highpass`/`bandpass`), `frequency`, `resonance`. Applied to a clip it works on the whole clip, so every transient in the mix (kick, snare, plucked attack) interacts with the filter's resonance as the cutoff moves. This is most musical where percussion is already sparse or has faded (an outro, a stripped bridge): "the room closing in." On a dense, drum-forward section expect audible ringing as the sweep crosses the drums' frequency content; keep `resonance` low (0 to 0.3).

**Sweep with automation**, not a separate sweep object:

```json
{"id": "n3", "type": "clip", "source": "a", "segment": "outro", "index": 1,
 "devices": [{"id": "flt", "type": "auto_filter", "filter": "lowpass", "frequency": 20000, "resonance": 0.2}],
 "automation": [{"target": "devices.flt.frequency", "points": [["0 beats", 20000], ["2 bars", 800]], "shape": "exp"}]}
```

**Transparent start** (no audible step where the effect begins): start the lowpass at 18000+ and use `shape: "exp"` so the cutoff barely moves at first.

A **static** filter (high-pass the low end, dull the top) is the `eq` device: `{"type": "eq", "low_cut": 400}` or `{"type": "eq", "high_cut": 4000}`.

## `reverb` — when and how

- **Reverb-on-reverb = bloom.** If a clip's tail already carries reverb (from the source recording, or a second reverb on the same signal), another reverb accumulates into mud. One return, used sparingly.
- **Return recipe (any track).** Put an `eq` `low_cut` of 200 to 300 Hz *before* the `reverb` on the return: low end in the reverb is what pumps the master limiter on a loud master. Use a moderate `decay` (1.5 to 2.5 s for a wash into an ending), `size` 50 to 60, `hi_cut` 4500 to 6000, `pre_delay` 20 to 30 ms.
- **Send level.** Peak around -9 to -13 dB. Never 0 dB on a `dry_wet: 100` return: the wet signal is as loud as the dry, and the limiter pays for it. A reverb that "squashes" is almost always a low-cut, level or decay problem, not a reason to drop the reverb.
- **Tails are kept.** A return rings out after the last clip that feeds it (up to 10 s, cut where it falls below -60 dB); `returns_tail_end` in `render.json` says when. You no longer need to pad the last clip.
- **No audible onset.** Don't ramp a send from `"-inf"` (true silence) and don't switch it on at a constant level mid-cut: the reverb is heard "turning on". Set a low base send (-24 to -30 dB) for the clip and ramp from it to the peak over at least 2 beats. For a clip-insert reverb, automate `devices.<id>.dry_wet` the same way, from a small non-zero value.
- Evidence (ticket 20261113-mbyv, loud EDM master): a full-range 3.5 s return with the send ramped -inf to 0 dB in 1 beat squashed (3.4 dB of limiting, rejected); low cut + 2 s + peak -9 dB cleared the limiter; a -26 dB base rising to -13 dB was accepted. Full recipes: `ending-transplant.md`.

## `delay`

`time` (note value, follows tempo), `feedback`, `filter_lo`/`filter_hi`, `ping_pong`. A delay on a return after a filter sweep inherits the swept tone in each repeat, which is usually what you want for an exit.

**`feedback` range determines the character, not just the repeat count:**

| `feedback` | Character | Use for |
|---|---|---|
| 0 - 40 | Distinct, countable echoes/slapback | A rhythmic accent; risks reading as a "clap" if the source has a percussive transient |
| 50 - 75 | Audible repeating pattern, decays within a few seconds | Mid-song texture, still clearly "an echo" |
| 85 - 95 | Repeats blur into a near-continuous decaying wash | Ambient beds, tape-loop textures |
| 95 max | The engine caps it; there is no infinite feedback | |

## Gain staging

`reverb` and `delay` add energy. The overlap of an `xfade` adds energy too (two clips at full level, e.g. `hold` on both sides). The master `limiter` (-1 dB by default) catches the sum and brings it back, but a limiter working hard sounds squashed.

- `render.json` reports `peak_dbfs` (after the master), `limiter_applied`, and under `qc` the measured loudness, true peak and `max_gain_reduction_db`; the `qc_limiting` warning fires when the limiter pulled the level down by more than 3 dB.
- If `qc_limiting` fires, lower the send level (by 3 dB), the clip `gain` (by 2 to 3 dB), or shorten the overlap, rather than relying on the limiter.
- Several wet stages in series (a clip reverb, then a return reverb, then a track delay) compound; check `peak_dbfs` after adding any.

## Order

Devices run in list order. **Static `eq`/filter first, then `auto_filter`, then `reverb`/`delay`, `utility` (gain) last.** Volume envelopes are clip `gain` automation and `fade_in`/`fade_out` handles, which run *before* the clip's devices: a fade-out on a clip with a reverb insert therefore fades the input, and the tail rings after the fade. For fading the *whole* sound including tails, automate the track's `gain` or the master.
