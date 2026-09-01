# Example: summer-party

Already-analyzed track — try the CLI and `compose()` API without running your own Modal
deploy first.

Audio: [Summer Party](https://pixabay.com/music/dance-summer-party-590004/) via Pixabay.

## Setup

```bash
mkdir -p .appdata/audio .appdata/maps/enriched
cp examples/summer-party/summer-party.mp3 .appdata/audio/
cp examples/summer-party/summer-party-map.json .appdata/maps/enriched/summer-party.json
recut status   # summer-party: ready
```

## Three cuts

`renders/` has the output for each, so you can compare the cuts.

### 1. `chorus-first` — reorder, fade-out only (61.9s)

`chorus` (hook) → `intro` → `verse` → `inst`, fade over the last 2 bars of `inst`.

```python
from recut.audio import Audio
from recut.map.parser import parse_recut_map
from recut.compositor import Clip, compose
from recut.compositor.effects import Fade
from recut.validator import validate

music_map = parse_recut_map(".appdata/maps/enriched/summer-party.json")
audio = Audio.load(".appdata/audio/summer-party.mp3")

nodes = [
    Clip("chorus"),
    Clip("intro"),
    Clip("verse"),
    Clip("inst", bars=7),
    Clip("inst", offset_bars=7, fx=[Fade(vol_start=1.0, vol_end=0.0, curve="qsin")]),
]

issues = validate(music_map, *nodes)
# expect a `sequence_boundaries` warning — first clip is "chorus" on purpose
result = compose(music_map, audio, *nodes)
```

### 2. `creative-edit` — hand-tuned, multiple effects (33.3s)

Second half of `inst` (fade-in + high-pass) → second half of `intro` → first half of
`chorus` (dry) → click-fade seam repair → the same `inst` tail reprised at the end,
band-passed into a gradually-building reverb — a full-circle bookend.

```python
from recut.audio import Audio
from recut.map.parser import parse_recut_map
from recut.compositor import Clip, XFade, compose
from recut.compositor.effects import Fade, FilterSweep, ReverbSweep
from recut.validator import validate

music_map = parse_recut_map(".appdata/maps/enriched/summer-party.json")
audio = Audio.load(".appdata/audio/summer-party.mp3")

nodes = [
    Clip("inst", offset_bars=4, bars=2, fx=[
        FilterSweep(filter_type="high", freq_start=400, freq_end=400),
        Fade(vol_start=0.5, vol_end=1.0, curve="qsin"),
    ]),
    Clip("inst", offset_bars=6, fx=[
        FilterSweep(filter_type="high", freq_start=400, freq_end=400),
    ]),
    Clip("intro", offset_bars=4),
    Clip("chorus", bars=4),
    XFade(ms=15),
    Clip("inst", offset_bars=4, fx=[
        FilterSweep(filter_type="high", freq_start=200, freq_end=200),
        FilterSweep(filter_type="low", freq_start=3000, freq_end=3000),
        ReverbSweep(wetness_start=0.0, wetness_end=0.6, reverb_type="room"),
    ]),
]

issues = validate(music_map, *nodes)
assert not any(i.severity == "error" for i in issues), issues
result = compose(music_map, audio, *nodes)
```

### 3. `ambient-soundscapes` — generative soundscape, reprocessed twice (65.8s)

Not a cut — a Fripp/Eno-style ambient piece from `inst`'s drum-free tail, looped 8x
through a single fixed effect chain (`Reverb`/`Delay` run continuously across all 8
repeats, no crossfades between them).

**Stage 1 — build it:**

```python
from recut.audio import Audio
from recut.map.parser import parse_recut_map
from recut.compositor import Clip, compose
from recut.compositor.effects import Delay, FilterSweep, Reverb
from recut.validator import validate

music_map = parse_recut_map(".appdata/maps/enriched/summer-party.json")
audio = Audio.load(".appdata/audio/summer-party.mp3")

node = Clip("inst", offset_bars=4, loop=8, fx=[
    FilterSweep(filter_type="high", freq_start=200, freq_end=200),
    FilterSweep(filter_type="low", freq_start=1400, freq_end=1400),
    Delay(delay_seconds=0.7, feedback=0.9, mix=0.15),
    Reverb(wetness=0.65, reverb_type="hall", room_size=0.97, damping=0.12),
])

issues = validate(music_map, node)
assert not any(i.severity == "error" for i in issues), issues
result = compose(music_map, audio, node)
```

**Stage 2 — reprocess the render through the same chain again, for real depth** (a
single pass reads thin). `chain()`, not `compose()` — no map/segment context for an
already-rendered mix. Peak-normalize between passes — without it, two cascaded
`feedback=0.9` delay passes clip hard (peak 5.56, 33.8% of samples over ceiling):

```python
import numpy as np
import soundfile as sf
from recut.audio import Audio
from recut.primitives.chain import chain
from recut.primitives.filter_sweep import filter_sweep
from recut.primitives.delay import delay
from recut.primitives.reverb import reverb
from recut.primitives.fade import fade
from recut.primitives.cut import cut

def peak_normalize(audio: Audio, target_peak: float = 0.85) -> Audio:
    peak = np.abs(audio.samples).max()
    if peak <= target_peak:
        return audio
    return Audio(audio.samples * (target_peak / peak), audio.sr)

reprocessed = chain(
    result,  # Stage 1 output
    filter_sweep(filter_type="high", freq_start=200, freq_end=200),
    filter_sweep(filter_type="low", freq_start=1400, freq_end=1400),
    delay(delay_seconds=0.7, feedback=0.75, mix=0.12),
    reverb(wetness=0.45, reverb_type="hall", room_size=0.97, damping=0.12),
)
reprocessed = peak_normalize(reprocessed, target_peak=0.85)

sr = reprocessed.sr
fade_in_s, fade_out_s = 3.0, 6.0
total_s = reprocessed.num_samples / sr
head = fade(vol_start=0.0, vol_end=1.0, curve="qsin")(cut(0, fade_in_s)(reprocessed))
middle = cut(fade_in_s, total_s - fade_out_s)(reprocessed)
tail = fade(vol_start=1.0, vol_end=0.0, curve="qsin")(cut(total_s - fade_out_s, total_s)(reprocessed))
final = Audio(np.concatenate([head.samples, middle.samples, tail.samples], axis=-1), sr)

sf.write("summer-party-ambient-soundscapes.mp3", final.samples.T, sr)
```
