#!/usr/bin/env python3
"""
Edit 1.5: Same as 1.4 + hall reverb on the intro for dramatic separation.

Output: labour-edit1.5.mp3
"""

import sys, subprocess, tempfile, os
import numpy as np
import librosa
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from primitives.cut import cut
from primitives.filter_sweep import filter_sweep
from primitives.fade import fade
from primitives.reverb import reverb
from primitives.xfade import xfade_join

SRC        = "testing/01/labour.mp3"
OUT        = "testing/01/labour-edit1.5.mp3"
CUT_START  = 51.15
CUT_END    = 89.01
SWEEP_DUR  = 6.0
FREQ_FLOOR = 220.0
FREQ_CEIL  = 20000.0
CURVE      = 6.0

print(f"Loading {SRC}...")
audio, sr = librosa.load(SRC, sr=None, mono=False)
if audio.ndim == 1:
    audio = np.stack([audio, audio])

intro_src = cut(audio, sr, CUT_START - SWEEP_DUR, CUT_START)
intro = filter_sweep(intro_src, sr, direction="open", duration=SWEEP_DUR,
                     freq_floor=FREQ_FLOOR, freq_ceil=FREQ_CEIL, curve=CURVE)
intro = fade(intro, vol_start=0.0, vol_end=1.0)
intro = reverb(intro, sr, wetness=0.5, reverb_type="hall")
# prepend silence so reverb has zero input at t=0 — kills the initial transient
silence = np.zeros((intro.shape[0], int(0.08 * sr)), dtype=intro.dtype)
intro = np.concatenate([silence, intro], axis=1)

main = cut(audio, sr, CUT_START, CUT_END)
result = xfade_join(intro, main, xfade_ms=60, sr=sr)

tmp = tempfile.mktemp(suffix=".wav")
sf.write(tmp, result.T, sr)
subprocess.run([
    "ffmpeg", "-y", "-i", tmp,
    "-codec:a", "libmp3lame", "-q:a", "2", OUT
], check=True, capture_output=True)
os.unlink(tmp)

print(f"✓ {OUT}  ({result.shape[1]/sr:.1f}s)")
