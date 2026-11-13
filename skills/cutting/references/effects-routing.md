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
- A section with prominent low end (bass-heavy, kick-driven) blooms in the low-mids: put an `eq` `low_cut` (150 to 250 Hz) on the clip, or on the return before the reverb, so only the highs feed the wash.
- High sends (0 dB, `dry_wet: 100` on the return) read as "dissolving into space", appropriate for exits, not mid-song.
- **Tails are kept.** A return rings out after the last clip that feeds it (up to 10 s, cut where it falls below -60 dB); `returns_tail_end` in `render.json` says when. You no longer need to pad the last clip.
- **No sudden onset.** Don't switch a send on at a constant level mid-cut: ramp it (`from: "-inf"`, `over` a beat or two) so the reverb doesn't "suddenly appear". For a clip-insert reverb, automate `devices.<id>.dry_wet` the same way.

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
