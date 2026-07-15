# Design Notes — recut MVP

---

## 1. User-facing API

The primary interface is a Python API. XML / YAML / a future UI are all valid on top of it —
they just serialize to the same structure. Don't design the Python API around any of those;
design it to be clean Python and let serialization come later.

**Preferred style — plain function call:**

```python
from recut import compose, Clip, Loop, Crossfade, FadeOut, load_map

compose(
    load_map("track.json"), "track.mp3",
    Clip("verse", index=2),
    Crossfade(beats=4),
    Loop(repeat=2, body=Clip("chorus")),
    FadeOut(beats=8),
)
```

**Alternative — fluent/builder style:**

```python
from recut import Composition, Clip, Loop, Crossfade, FadeOut, load_map

(
    Composition(load_map("track.json"), "track.mp3")
    .add(Clip("verse", index=2))
    .add(Crossfade(beats=4))
    .add(Loop(Clip("chorus"), repeat=2))
    .add(FadeOut(beats=8))
    .render("output.mp3")
)
```

Both styles use the same node objects (`Clip`, `Loop`, etc.) — `compose()` and `Composition`
are just two interfaces to the same compositor.

`Clip`, `Loop`, `Crossfade`, `FadeOut` are plain data objects (no logic). `Composition` holds
the sequence; `.render()` walks the nodes, looks up section timestamps in the map, and calls
the primitives.

**On section indexing:** `Clip("verse", index=2)` uses the global `index` field already in the
map — that's fine for the programmatic API. Per-label indexing ("second verse") is a UI
concern, implement it when building the UI layer.

**React/JSX is out of scope.** Remotion uses React because it renders video frame-by-frame —
React's reconciler does real work there. Audio cutting is a one-shot transformation with no
render loop. JSX without React is just XML. Use XML directly if you want that syntax, or stay
with the Python API.

---

## 2. Primitives — Audio abstraction

Every primitive currently takes `(audio: np.ndarray, sr: int, ...) → np.ndarray` and handles
mono/stereo branching internally. Wrap this into an `Audio` class so the representation is
hidden and `sr` never drifts from its samples.

```python
class Audio:
    def __init__(self, samples: np.ndarray, sr: int):
        self.samples = samples
        self.sr = sr

    @property
    def is_mono(self) -> bool:
        return self.samples.ndim == 1

    @property
    def num_samples(self) -> int:
        return self.samples.shape[-1]

    def apply_to_channels(self, fn) -> "Audio":
        if self.is_mono:
            return Audio(fn(self.samples), self.sr)
        return Audio(
            np.stack([fn(self.samples[i]) for i in range(self.samples.shape[0])]),
            self.sr
        )
```

All primitives become:

```python
def cut(audio: Audio, start: float, end: float) -> Audio:
    s = int(round(start * audio.sr))
    e = int(round(end * audio.sr))
    return audio.apply_to_channels(lambda ch: ch[s:e])

def fade(audio: Audio, vol_start: float = 0.0, vol_end: float = 1.0) -> Audio:
    envelope = np.linspace(vol_start, vol_end, audio.num_samples)
    return audio.apply_to_channels(lambda ch: ch * envelope)
```

`apply_to_channels` handles mono/stereo once. Primitives that are pure channel-wise math
(cut, fade, filter, eq) use it and never branch on shape. DSP effects with genuine stereo
semantics (reverb width, delay) take the `Audio` object directly and call pedalboard with
`audio.samples` — pedalboard handles stereo natively.

`chain()` simplifies to:

```python
def chain(audio: Audio, *steps) -> Audio:
    for fn, kwargs in steps:
        audio = fn(audio, **kwargs)
    return audio
```

**Optional: factory-style primitives.** An alternative is to make each primitive a factory —
a function that takes only parameters and returns an `Audio → Audio` transform:

```python
def cut(start: float, end: float):
    def apply(audio: Audio) -> Audio:
        s = int(round(start * audio.sr))
        e = int(round(end * audio.sr))
        return audio.apply_to_channels(lambda ch: ch[s:e])
    return apply

result = cut(1.0, 3.0)(audio)
```

With this style `chain` becomes a plain loop over callables — no `kwargs` tuple unpacking needed:

```python
def chain(audio: Audio, *transforms) -> Audio:
    for t in transforms:
        audio = t(audio)
    return audio
```

More importantly, once the `Composition` API exists, `chain` probably disappears from the
public API entirely — `Composition.render()` is already doing the same loop internally.

---

## 3. Swappable analysis pipeline

The ML analysis (Modal) should sit behind an interface so it can be replaced later without
touching anything else.

```python
class AnalysisPipeline:
    def analyze(self, audio_path: str) -> dict:
        raise NotImplementedError

class ModalPipeline(AnalysisPipeline):
    def analyze(self, audio_path: str) -> dict:
        # current modal_chordmini.py logic

class LocalPipeline(AnalysisPipeline):
    def analyze(self, audio_path: str) -> dict:
        # future: local models, different service, etc.
```

The rest of the code calls `pipeline.analyze(path)` only. `make_map.py` (the local enrichment
step) sits outside this abstraction — it runs locally regardless of which pipeline produced the
raw JSON, and that's correct.

---

## 4. Testing

**Primitives** are pure functions (`Audio → Audio`) with no side effects and no external
dependencies. Test them with a synthetic audio clip — a short sine wave generated in the test:

```python
import numpy as np
from recut.audio import Audio

def sine(duration=1.0, freq=440, sr=44100) -> Audio:
    t = np.linspace(0, duration, int(sr * duration))
    return Audio(np.sin(2 * np.pi * freq * t).astype(np.float32), sr)

def test_cut_length():
    audio = sine(duration=4.0)
    result = cut(audio, start=1.0, end=3.0)
    assert result.num_samples == 2 * 44100

def test_fade_ends_at_zero():
    audio = sine()
    result = fade(audio, vol_start=1.0, vol_end=0.0)
    assert abs(result.samples[-1]) < 1e-6
```

No audio files needed, tests run in milliseconds.

**`make_map.py` utilities** (`snap_to_downbeat`, `bars_in`, `loudness_rms_db`) are currently
nested inside `run()` — move them to module level so they can be imported and tested directly.

**The analysis pipeline** is the one piece that's hard to unit test (GPU, network, slow).
The `AnalysisPipeline` abstraction makes this easy: write a `FakePipeline` that returns a
hardcoded dict, and use it everywhere in tests. Only integration tests hit the real Modal
pipeline.

**The compositor** (`Composition.render()`) can be tested with a `FakePipeline` + a
small hand-written map JSON + a short synthetic audio file.

---

## 5. Implementation issues to fix

**`validate()` in `make_map.py` has a bug.** The missing-key branch tries to access
`data[key]` inside the error message — but if the key is missing, that raises `KeyError`
before the message is constructed. Separate the two cases:

```python
if key not in data:
    raise ValueError(f"missing required field: {key}")
if not isinstance(data[key], expected_type):
    raise ValueError(f"{key}: expected {expected_type}, got {type(data[key])}")
```

**`duration` in `make_map.py` uses the last beat timestamp** (`data["beats"][-1]`), not the
actual audio length. Beat tracking often drops out before the true end. Use
`audio.shape[-1] / sr` instead — the audio is already loaded.

**`eq` uses `type` as a parameter name**, shadowing Python's built-in. Rename to
`filter_type` or `btype`.

**`combine_stems` does not follow the `fn(audio, sr, ...)` convention** — it takes `*stems`
instead of a single audio argument. It cannot be used in `chain()`. It's a useful utility but
should not be listed alongside the primitives. Keep it separate and document the distinction.

**`eq_sweep` overlaps significantly with `filter_sweep`.** Decide which one is canonical and
delete the other. The CHANGELOG only documents `filter_sweep`.

**`primitives/` has no `__init__.py`** — it is not a Python package and cannot be imported
with `from primitives import cut`. Add `__init__.py` and export the public functions from it.