#!/usr/bin/env python3
"""
Apply edit1.1: eq_sweep intro with more aggressive low-pass (voice barely intelligible)
               sweeping to fully open at the cut point.

Output: labour-edit1.1.mp3
"""

import sys, subprocess, tempfile, os
import numpy as np
import librosa
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from primitives.cut import cut
from primitives.eq_sweep import eq_sweep

SRC         = "testing/01/labour.mp3"
OUT         = "testing/01/labour-edit1.1.mp3"
CUT_START   = 51.15
CUT_END     = 89.01
SWEEP_DUR   = 6.0
FREQ_START  = 800.0   # Hz — voice barely intelligible (words just recognisable)
FREQ_END    = 20000.0 # Hz — fully open at cut point

print(f"Loading {SRC}...")
audio, sr = librosa.load(SRC, sr=None, mono=False)
if audio.ndim == 1:
    audio = np.stack([audio, audio])

main = cut(audio, sr, CUT_START, CUT_END)
print(f"Main cut: {main.shape[1]/sr:.2f}s")

sweep_source = cut(audio, sr, CUT_START - SWEEP_DUR, CUT_START)
intro = eq_sweep(sweep_source, sr, duration=SWEEP_DUR, freq_start=FREQ_START, freq_end=FREQ_END)
print(f"Sweep intro: {intro.shape[1]/sr:.2f}s  ({FREQ_START}Hz → {FREQ_END}Hz)")

result = np.concatenate([intro, main], axis=1)
print(f"Total: {result.shape[1]/sr:.2f}s")

tmp = tempfile.mktemp(suffix=".wav")
sf.write(tmp, result.T, sr)
subprocess.run([
    "ffmpeg", "-y", "-i", tmp,
    "-codec:a", "libmp3lame", "-q:a", "2", OUT
], check=True, capture_output=True)
os.unlink(tmp)

print(f"\n✓ {OUT}")
