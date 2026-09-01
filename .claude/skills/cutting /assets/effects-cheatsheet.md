# Effects Cheatsheet

Quick lookup — quote directly, don't paraphrase. Full rationale in `../references/effects-routing.md`.

## Reverb presets (`src/recut/primitives/reverb.py` `PRESETS`)

| `reverb_type` | `room_size` | `damping` | `width` | Character |
|---|---|---|---|---|
| `"room"` | 0.35 | 0.7 | 0.5 | Small, intimate |
| `"hall"` | 0.85 | 0.3 | 0.9 | Large, spacious — default |
| `"plate"` | 0.6 | 0.1 | 1.0 | Bright, washy |

Any field is overridable per-call: `Reverb(reverb_type="hall", damping=0.5)`.

## Wetness guide

| `wetness` | Reads as |
|---|---|
| 0.85+ | Fully ambient / ghost — no dry signal |
| 0.55 | Hall send — room feel, source still clear |
| 0.35–0.4 | Subtle space — adds air |
| 0.12–0.2 | Very light "room mic" |

## `Curve` (string type — `fade`, `xfade`)

`linear` | `log` (raises if either endpoint ≤ 0) | `exp` | `qsin` (equal-power, best default for crossfades)

## `filter_sweep`/`FilterSweep` curve (numeric — NOT the same as `Curve` above)

`1.0` = linear. `>1.0` = stays near `freq_start` longer, drops fast near the end. `<1.0` = moves fast then slows. `2.5` is a good "lingers, then closes" default for an exit sweep.

## No `eq` — static filter workaround

```python
FilterSweep(filter_type="high", freq_start=400.0, freq_end=400.0)  # static high-pass
FilterSweep(filter_type="low",  freq_start=4000.0, freq_end=4000.0)  # static low-pass
```
