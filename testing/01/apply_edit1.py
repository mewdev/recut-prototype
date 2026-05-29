#!/usr/bin/env python3
"""
Apply edit1: eq_sweep intro + hard cut [51.15s–89.01s]

Output: labour-edit1.mp3
"""

import sys, subprocess, tempfile, os
import numpy as np
import librosa
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from primitives.cut import cut
from primitives.eq_sweep import eq_sweep

SRC         = "testing/01/labour.mp3"
OUT         = "testing/01/labour-edit1.mp3"
CUT_START   = 51.15
CUT_END     = 89.01
SWEEP_DUR   = 6.0    # seconds of intro sweep (max 8)
FREQ_START  = 300.0  # Hz — muffled start
FREQ_END    = 18000.0

print(f"Loading {SRC}...")
audio, sr = librosa.load(SRC, sr=None, mono=False)
if audio.ndim == 1:
    audio = np.stack([audio, audio])

# 1. Cut the main section
main = cut(audio, sr, CUT_START, CUT_END)
print(f"Main cut: {main.shape[1]/sr:.2f}s")

# 2. Take the same audio just before the cut as the sweep source
sweep_source = cut(audio, sr, CUT_START - SWEEP_DUR, CUT_START)
intro = eq_sweep(sweep_source, sr, duration=SWEEP_DUR, freq_start=FREQ_START, freq_end=FREQ_END)
print(f"Sweep intro: {intro.shape[1]/sr:.2f}s  ({FREQ_START}Hz → {FREQ_END}Hz)")

# 3. Join: intro + main (hard join — intro ends at full EQ so no pop)
result = np.concatenate([intro, main], axis=1)
print(f"Total: {result.shape[1]/sr:.2f}s")

# 4. Write via soundfile → ffmpeg → mp3
tmp = tempfile.mktemp(suffix=".wav")
sf.write(tmp, result.T, sr)
subprocess.run([
    "ffmpeg", "-y", "-i", tmp,
    "-codec:a", "libmp3lame", "-q:a", "2", OUT
], check=True, capture_output=True)
os.unlink(tmp)

print(f"\n✓ {OUT}")
