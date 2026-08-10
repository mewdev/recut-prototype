import os

import soundfile as sf

from audio import Audio
from map_parser import OurMapParser
from primitives.cut import cut

MAP = "map/examples/end_of_beginning-map-v0_1.json"
MP3 = "mp3/end_of_beginning.mp3"

parser = OurMapParser(MAP)
audio = Audio.load(MP3)

os.makedirs("output", exist_ok=True)

chorus1 = parser.get_segment("chorus", index=1)
bridge = parser.get_segment("bridge", index=1)

sf.write("output/chorus1_raw.wav", cut(chorus1["start"], chorus1["end"])(audio).samples.T, audio.sr)
sf.write("output/bridge_raw.wav", cut(bridge["start"], bridge["end"])(audio).samples.T, audio.sr)

print(f"chorus1: {chorus1['start']:.3f} → {chorus1['end']:.3f}")
print(f"bridge:  {bridge['start']:.3f} → {bridge['end']:.3f}")
