"""
Export individual sections from MUF sample-exact boundaries.

MUF sections mapped to our labels (where aligned):
  MUF[0] 00_intro       4085      – 136730     (0.09–3.10s)
  MUF[1] 01_verse_01    136730    – 1592003     (3.10–36.10s)
  MUF[2] 02_chorus_01   1592003   – 2650252     (36.10–60.10s)
  MUF[3] 03_verse_02    2650252   – 3907201     (60.10–88.60s)  ← merges our verse4+verse5
  MUF[4] 04_chorus_02   3907201   – 4833470     (88.60–109.60s)
  MUF[5] 05_bridge_01  4965770   – 5892240     (112.61–133.61s) ← split at beat/chord change; first 3s of MUF[5] is chorus tail
  MUF[6] 06_chorus_03   5892240   – 6950569     (133.61–157.61s)
  MUF[7] 07_silence     6950569   – 7025102     (157.61–159.30s)
"""

import os

import numpy as np
import soundfile as sf

AUDIO_IN  = "mp3/end_of_beginning.mp3"
OUTPUT_DIR = "output/muf_sections"

# (start_sample, end_sample, label)
MUF_SECTIONS = [
    (4085,    136730,   "00_intro"),
    (136730,  1592003,  "01_verse_01"),
    (1592003, 2650252,  "02_chorus_01"),
    (2650252, 3907201,  "03_verse_02"),
    (3907201, 4833470,  "04_chorus_02"),
    (4965770, 5892240,  "05_bridge_01"),  # 112.61s — beat + chord change G:maj→A:maj
    (5892240, 6950569,  "06_chorus_03"),
    (6950569, 7025102,  "07_silence"),
]

def main():
    audio, sr = sf.read(AUDIO_IN, always_2d=True)
    audio = audio.T.astype(np.float32)
    assert sr == 44100

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for start, end, label in MUF_SECTIONS:
        segment = audio[:, start:end]
        path = os.path.join(OUTPUT_DIR, f"{label}.wav")
        sf.write(path, segment.T, sr)
        print(f"{label}: {start/sr:.2f}–{end/sr:.2f}s  ({(end-start)/sr:.2f}s)  → {path}")

if __name__ == "__main__":
    main()
