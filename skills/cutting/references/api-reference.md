# API Reference

Ground truth for the current `src/recut` call surface. This file is checked by `scripts/check_skill.py` against live signatures — if this drifts from the code, the drift check fails `pytest tests/`. Keep every signature here byte-for-byte matched to source.

## `Audio` (`src/recut/audio.py`)

```python
class Audio:
    samples: np.ndarray   # shape (n_samples,) mono or (n_channels, n_samples)
    sr: int

    @classmethod
    def load(cls, path: str) -> "Audio": ...
    is_mono: bool
    num_samples: int
    num_channels: int
    def apply_to_channels(self, fn) -> "Audio": ...
```

## Primitives (`src/recut/primitives/`) — curried, `fn(**params) -> (audio: Audio) -> Audio`

Every primitive except `chain` and `xfade` returns a unary closure over `Audio`. Compose with `chain(audio, prim1(...), prim2(...), ...)` — bare curried callables passed positionally, **not** `(fn, kwargs)` tuples.

```python
cut(start: float, end: float)
# required, no defaults — slices [start, end) seconds

fade(vol_start: float = 0.0, vol_end: float = 1.0, curve: Curve = "linear")
# Curve = "linear" | "log" | "exp" | "qsin"

filter_sweep(
    filter_type: Literal["low", "high"] = "low",
    freq_start: float = 200.0,      # Hz, cutoff at t=0
    freq_end: float = 20000.0,      # Hz, cutoff at t=end
    duration: float | None = None,  # seconds; None = full audio length
    curve: float = 1.0,             # NUMERIC exponent, not the Curve string type:
                                     # 1.0 = linear, >1 lingers near freq_start, <1 moves fast then slows
)

reverb(
    wetness: float = 0.4,           # 0.0 dry .. 1.0 fully wet
    reverb_type: Literal["room", "hall", "plate"] = "hall",
    room_size: float | None = None, # overrides preset
    damping: float | None = None,   # overrides preset
    width: float | None = None,     # overrides preset
)

reverb_sweep(
    wetness_start: float = 0.0,     # mix at t=0
    wetness_end: float = 0.4,       # mix at the end of the ramp
    reverb_type: Literal["room", "hall", "plate"] = "hall",
    room_size: float | None = None,
    damping: float | None = None,
    width: float | None = None,
    duration: float | None = None,  # seconds the ramp takes; None = whole clip;
                                     # holds at wetness_end past duration if shorter
    curve: Curve = "qsin",          # envelope shape, see curves.make_envelope
                                     # ("log" needs both bounds > 0 — can't start silent)
)
# `reverb()` applies a fixed wetness to the whole clip — steps in abruptly if the
# clip starts mid-composition. `reverb_sweep()` ramps the wet/dry mix instead
# (dry and fully-wet buffers cross-mixed with a make_envelope() curve — pedalboard
# itself has no wet_level automation).

delay(
    delay_seconds: float = 0.5,
    feedback: float = 0.0,          # 0 = one echo, 1.0 = infinite repeats
    mix: float = 0.5,
)

xfade(xfade_ms: float = 500, curve: Curve = "qsin")
# BINARY: xfade(ms, curve)(a: Audio, b: Audio) -> Audio
# raises on sample-rate mismatch, channel-layout mismatch, or xfade_ms longer than either clip

chain(audio: Audio, *transforms) -> Audio
```

**There is no `eq` primitive.** See `effects-routing.md` for the workaround.

## Compositor node types (`src/recut/compositor/nodes.py`)

`Clip` and `XFade` are dataclasses; shown here as their equivalent constructor calls:

```python
Clip(
    segment_name: SegmentName,
    index: int = 1,
    source: Optional[str] = None,
    bars: Optional[float] = None,
    beats: Optional[float] = None,
    offset_bars: Optional[float] = None,
    offset_beats: Optional[float] = None,
    loop: Optional[int] = None,
    fx: list[Effect] = [],
)

XFade(
    ms: float = 500.0,
    curve: Curve = "qsin",
    beats: Optional[float] = None,
)
```

- `index`: 1st occurrence of this label, 2nd, ...
- `source`: placeholder only — not read by `compose()` today, see `known-limitations.md`
- `offset_bars`/`offset_beats`: skip N bars/beats from segment start before cutting
- `loop`: repeat the extracted clip N times, THEN apply `fx`
- `XFade.curve`: `qsin` = equal-power, best default for music
- `XFade.beats`: if set, duration resolved from map BPM instead of `ms`

`Node = Union[Clip, XFade]`

`bars`/`beats` set the clip length from the (possibly offset/snapped) start; both raise `ValueError` in `compose()` if they'd run past the segment's end. `XFade` sits *between* two `Clip`s in the node sequence and consumes the previous clip — it can't be first or last, and two `XFade`s can't be adjacent.

## Effects (`src/recut/compositor/effects.py`) — typed, serializable `fx` entries

Each `Effect` subclass's fields mirror its primitive's kwargs exactly (`to_fn()` calls `primitive(**asdict(self))`):

```python
Fade(vol_start: float = 0.0, vol_end: float = 1.0, curve: Curve = "linear")
Reverb(wetness: float = 0.4, reverb_type: ReverbType = "hall", room_size=None, damping=None, width=None)
ReverbSweep(wetness_start: float = 0.0, wetness_end: float = 0.4, reverb_type: ReverbType = "hall", room_size=None, damping=None, width=None, duration=None, curve: Curve = "qsin")
Delay(delay_seconds: float = 0.5, feedback: float = 0.0, mix: float = 0.5)
FilterSweep(filter_type: FilterType = "low", freq_start: float = 200.0, freq_end: float = 20000.0, duration=None, curve: float = 1.0)
```

Only these 5 exist (`EFFECT_TYPES` in `effects.py`). Use them in `Clip(fx=[...])`.

## `compose()` (`src/recut/compositor/__init__.py`)

```python
compose(music_map: MusicMap, audio: Audio, *nodes: Node) -> Audio
```

Takes **one** `Audio` — the full mix. Runs each `Clip` through: resolve segment → snap/offset → cut → loop (if set) → apply `fx` in list order → consume any preceding `XFade`. Concatenates the result. Effects always apply to the whole mix, not an isolated instrument.

## `validate()` (`src/recut/validator/__init__.py`)

```python
validate(music_map: MusicMap, *nodes: Node) -> list[ValidationResult]
ValidationResult(severity: Literal["error", "warning", "info"], message: str, node: AudioNode, source: Optional[str] = None)
```

See `validation-workflow.md` for what the current rules actually check.

## Map helpers (`src/recut/map/parser.py`)

```python
parse_recut_map(map_path: str | Path) -> MusicMap
get_segment(music_map: MusicMap, segment_name: SegmentName, index: int = 1) -> EnrichedSegment
get_bpm(music_map: MusicMap) -> float
bars_to_seconds(music_map: MusicMap, bars: float) -> float
beats_to_seconds(music_map: MusicMap, beats: float) -> float
first_segment(music_map: MusicMap) -> EnrichedSegment
last_segment(music_map: MusicMap) -> EnrichedSegment
```

## CLI

```bash
recut validate <composition-name>   # validate() only, exit non-zero on any error
recut render <composition-name> [--out PATH] [--force]  # validate, then compose() + write audio
```

`--force` renders despite `error`-severity validation results (still prints them). Output defaults to `.appdata/renders/<name>.mp3`.

## Where to write agent-authored cut scripts

There's no MCP tool or REPL for the compositor — build a cut by writing a plain, throwaway `.py` script and running it with `/Users/michal/miniconda3/envs/recut/bin/python script.py`, same as any other coding task. Put it in the session's scratch directory, not the repo — it's disposable once run. It ends one of two ways:

- **One-shot render**: script itself calls `compose()` and writes the output audio (path 2 below) — nothing needs to persist.
- **Saved for CLI reuse**: script calls `save_composition(...)` (`recut.project`) to write `.appdata/compositions/<name>.json`, then `recut validate <name>` / `recut render <name>` do the rest — the script can be discarded once the composition is saved.

## Minimal end-to-end example

```python
import soundfile as sf
from recut.audio import Audio
from recut.map.parser import parse_recut_map
from recut.compositor import Clip, XFade, compose
from recut.compositor.effects import Fade, Reverb
from recut.validator import validate

music_map = parse_recut_map(".appdata/maps/enriched/midnight_run-map.json")
audio = Audio.load(".appdata/audio/midnight_run.mp3")

nodes = [
    Clip("intro"),
    XFade(beats=4),
    Clip("verse"),
    Clip("chorus", loop=2, fx=[Reverb(wetness=0.35, reverb_type="hall"), Fade(vol_start=1.0, vol_end=0.0)]),
]

issues = validate(music_map, *nodes)
assert not any(i.severity == "error" for i in issues), issues

result = compose(music_map, audio, *nodes)
sf.write("midnight_run-cut.mp3", result.samples.T, result.sr)
```
