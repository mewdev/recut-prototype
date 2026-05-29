#!/usr/bin/env python3
"""
Edit 1.2: DJ-style low-pass filter sweep intro (60Hz → fully open, log curve)
          Hard cut [51.15s–89.01s], sweep duration = 6s.

Output: labour-edit1.2.mp3
"""

import sys, subprocess, tempfile, os
import numpy as np
import librosa
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from primitives.cut import cut
from primitives.filter_sweep import filter_sweep

SRC        = "testing/01/labour.mp3"
OUT        = "testing/01/labour-edit1.2.mp3"
CUT_START  = 51.15
CUT_END    = 89.01
SWEEP_DUR  = 6.0
FREQ_START = 60.0    # Hz — near silence, only sub-bass kicks through
FREQ_END   = 20000.0 # Hz — fully open at cut point

print(f"Loading {SRC}...")
audio, sr = librosa.load(SRC, sr=None, mono=False)
if audio.ndim == 1:
    audio = np.stack([audio, audio])

main = cut(audio, sr, CUT_START, CUT_END)
sweep_source = cut(audio, sr, CUT_START - SWEEP_DUR, CUT_START)
intro = filter_sweep(sweep_source, sr, duration=SWEEP_DUR, freq_start=FREQ_START, freq_end=FREQ_END)
print(f"Sweep: {SWEEP_DUR}s  {FREQ_START}Hz → {FREQ_END}Hz (log)")

result = np.concatenate([intro, main], axis=1)

tmp = tempfile.mktemp(suffix=".wav")
sf.write(tmp, result.T, sr)
subprocess.run([
    "ffmpeg", "-y", "-i", tmp,
    "-codec:a", "libmp3lame", "-q:a", "2", OUT
], check=True, capture_output=True)
os.unlink(tmp)

print(f"✓ {OUT}  ({result.shape[1]/sr:.1f}s)")
