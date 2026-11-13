# Effects Cheatsheet

Quick lookup — quote directly, don't paraphrase. The format is `docs/PLAN.md` §3.2; the routing rationale is in `../references/effects-routing.md`.

## Units (one rule per kind of value)

| Kind | Written as | Examples |
|---|---|---|
| Time | string with a unit; musical units follow the clip's source tempo | `"1/4"`, `"1/8."` (dotted), `"1/8t"` (triplet), `"3 beats"`, `"2 bars"`, `"250ms"`, `"3.5s"` |
| Level (`gain`, `volume`, sends, `ceiling`, EQ band `gain`) | number in **dB**, or `"-inf"` | `-6`, `0`, `"-inf"` |
| Percentage (`dry_wet`, `feedback`, `size`, `width`) | number 0–100, as Ableton shows it (`width` on `utility` goes to 200) | `dry_wet: 40` |
| Frequency | number in Hz | `frequency: 800`, `hi_cut: 6000` |
| Pan (track) | -50 (L) … 50 (R) | `pan: 0` |

## Shapes (fades, xfades, automation)

| Shape | Curve 0→1 | Use |
|---|---|---|
| `linear` | straight line | default for sends and parameters |
| `equal_power` | quarter sine (`qsin` is accepted as an alias) | crossfades between different material, fade-ins |
| `exp` | slow start, fast end (`t²`) | send swells ("blooms on the last beat"), fade-outs that linger |
| `log` | fast start, slow end (`√t`) | quick attack then settle |
| `hold` | full level for the whole overlap/ramp | the incoming "hit" (`in_shape`), or the outgoing dry signal under a wash (`out_shape`) |

A fade-out uses the mirror of the shape. Level automation (`gain`, `sends.*`) interpolates in linear gain, so `-inf → 0` with `exp` swells from true silence. Frequency parameters move in log-frequency.

## Devices

| Device | Parameters (default) | Notes |
|---|---|---|
| `utility` | `gain` (0 dB), `width` (100; 0 = mono, 200 = double) | automatable: `gain`, `width` |
| `eq` | `low_cut` Hz, `high_cut` Hz, `bands: [{frequency, gain dB, q (0.71)}]` | cuts are 12 dB/oct; static high-pass: `{"type": "eq", "low_cut": 400}`. Automatable: `low_cut`, `high_cut` |
| `auto_filter` | `filter` (`lowpass`/`highpass`/`bandpass`), `frequency` (20000), `resonance` (0–1.25, default 0) | 12 dB/oct. Automatable: `frequency`, `resonance`. A transparent start: lowpass at 18000+ then sweep down |
| `reverb` | `decay` ("2s"), `pre_delay` ("0ms"), `size` (50), `hi_cut` (8000), `width` (100), `dry_wet` (100) | automatable: `dry_wet`, `hi_cut`. On a return keep `dry_wet: 100` |
| `delay` | `time` ("1/8"), `feedback` (30, max 95), `ping_pong` (false), `filter_lo` (100), `filter_hi` (8000), `dry_wet` (100) | filters sit in the feedback path, so each repeat is darker. Automatable: `dry_wet`, `feedback`, `filter_lo`, `filter_hi` |
| `limiter` | `ceiling` (-1 dB) | only reduces the signal if it is over the ceiling. The master has one at -1 dB by default |

Clip `devices` run after the clip's gain and fades; their tails ring on past the clip. Track and master `devices` run on the summed track. Return devices run once over everything sent to the return.

## Reverb: decay and what it sounds like

`decay` is approximate (the engine maps it to a room-size table: 0.53 s to 9.5 s, clamped outside; `size` scales it from x0.7 to x1.3).

| `decay` | Reads as |
|---|---|
| `"0.6s"`–`"1s"` | small room, intimate |
| `"1.5s"`–`"2.5s"` | hall, the usual space for a join |
| `"3s"`–`"4s"` | big hall / exit wash |
| `"6s"`+ | cathedral; will blur fast material |

Send level for a reverb return: `-12` to `-9` is "air", `-6` is a clear room, `0` is a wash (dry stays as is). The wet signal is level-matched, so a send at 0 dB is about as loud as the dry. `hi_cut` 5000–7000 keeps tails soft; `pre_delay` 10–30 ms keeps the source clear.

## Delay: `time` in note values

| `time` | Length at 120 BPM | Feel |
|---|---|---|
| `"1/4"` | 500 ms | one echo per beat |
| `"1/8"` | 250 ms | straight eighths |
| `"1/8."` | 375 ms | dotted eighth, the classic rhythmic echo |
| `"1/8t"` | 167 ms | triplet |
| `"1/16"` | 125 ms | fast, thickening |

`feedback`: 0–40 distinct echoes, 50–75 a pattern that decays in a few seconds, 85–95 a near-continuous wash (a bed, not an accent).

## Automation

```json
{"target": "sends.A", "from": "-inf", "to": 0, "over": "1 beat", "at": "end", "shape": "exp"}
{"target": "devices.flt.frequency", "points": [["0 beats", 20000], ["2 bars", 800]], "shape": "exp"}
```

- Targets: `gain`, `sends.<return id>`, `devices.<device id>.<parameter>`. Clips, tracks and returns can carry automation.
- Times are relative to the clip's start (for tracks and returns: the start of the timeline). `at: "end"` means the ramp *ends* at the clip's end; `"start"` is the default; any time string also works.
- Before a ramp starts the value is its `from`; after it ends, its `to`. Automation replaces the static `gain`/send value.
- A ramp longer than its clip is an error: the message says so.

## Joins (`xfade`)

| Goal | `xfade` |
|---|---|
| Normal blend | `{"length": "2 beats", "shape": "equal_power"}` |
| Hit on top (new part at full level at once) | `{"length": "30ms", "in_shape": "hold"}` |
| Short overlap, both sides at full level | `{"length": "30ms", "out_shape": "hold", "in_shape": "hold"}` |
| Dry signal stays until the new part lands | `{"length": "30ms", "out_shape": "hold", "in_shape": "equal_power"}` |

If a clip is shorter than the requested length, the engine shortens the join and reports `xfade_clamped`.
