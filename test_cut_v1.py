"""
Cut v1 — no effects
Layout: intro × 2 → chorus 1 → bridge 1
Map:    end_of_beginning-map-v0_1-edited.json
"""

import os

import soundfile as sf

from compositor import Clip, Loop, compose
from map_parser import OurMapParser

MAP = "map/examples/end_of_beginning-map-v0_1-edited.json"
MP3 = "mp3/end_of_beginning.mp3"

parser = OurMapParser(MAP)
os.makedirs("output", exist_ok=True)

result = compose(
    parser,
    MP3,
    Loop("intro",  times=2,  index=1),
    Clip("chorus", index=1),
    Clip("bridge", index=1),
)

out = "output/cut_v1.wav"
sf.write(out, result.samples.T, result.sr)

dur = result.samples.shape[-1] / result.sr
print(f"Written: {out}  ({dur:.1f}s)")
