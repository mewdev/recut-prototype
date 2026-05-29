#!/usr/bin/env python3
"""
Edit 2.1: Intro from 1.5 (filter sweep + reverb) + creative ending.

Ending treatment (last 5s of cut):
  — delay at half-beat (361ms @ 83 BPM) with feedback tail
  — filter sweep close (full → 300Hz)
  — fade out to silence
  All timed to land on the downbeat at 89.01s.

Output: labour-edit2.1.mp3
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
from primitives.delay import delay
from primitives.xfade import xfade_join

SRC          = "testing/01/labour.mp3"
OUT          = "testing/01/labour-edit2.1.mp3"
CUT_START    = 51.15
CUT_END      = 89.01
SWEEP_DUR    = 6.0
FREQ_FLOOR   = 220.0
FREQ_CEIL    = 20000.0
CURVE        = 6.0
ENDING_DUR   = 5.0    # seconds of ending treatment before CUT_END
BPM          = 83
HALF_BEAT    = (60 / BPM) / 2  # 0.361s

print(f"Loading {SRC}...")
audio, sr = librosa.load(SRC, sr=None, mono=False)
if audio.ndim == 1:
    audio = np.stack([audio, audio])

# ── Intro (same as 1.5) ───────────────────────────────────────────────────────
intro_src = cut(audio, sr, CUT_START - SWEEP_DUR, CUT_START)
intro = filter_sweep(intro_src, sr, direction="open", duration=SWEEP_DUR,
                     freq_floor=FREQ_FLOOR, freq_ceil=FREQ_CEIL, curve=CURVE)
intro = fade(intro, vol_start=0.0, vol_end=1.0)
intro = reverb(intro, sr, wetness=0.5, reverb_type="hall")
silence = np.zeros((intro.shape[0], int(0.08 * sr)), dtype=intro.dtype)
intro = np.concatenate([silence, intro], axis=1)

# ── Main body (cut without the ending zone) ───────────────────────────────────
body_end = CUT_END - ENDING_DUR
body = cut(audio, sr, CUT_START, body_end)

# ── Ending zone ───────────────────────────────────────────────────────────────
ending_src = cut(audio, sr, body_end, CUT_END)
ending = delay(ending_src, sr, delay_seconds=HALF_BEAT, feedback=0.45, wetness=0.45)
ending = filter_sweep(ending, sr, direction="close", duration=ENDING_DUR,
                      freq_floor=300.0, freq_ceil=FREQ_CEIL, curve=1.5)
ending = fade(ending, vol_start=1.0, vol_end=0.0)

# ── Join ──────────────────────────────────────────────────────────────────────
mid = xfade_join(intro, body, xfade_ms=60, sr=sr)
result = xfade_join(mid, ending, xfade_ms=80, sr=sr)

tmp = tempfile.mktemp(suffix=".wav")
sf.write(tmp, result.T, sr)
subprocess.run([
    "ffmpeg", "-y", "-i", tmp,
    "-codec:a", "libmp3lame", "-q:a", "2", OUT
], check=True, capture_output=True)
os.unlink(tmp)

print(f"✓ {OUT}  ({result.shape[1]/sr:.1f}s)")
print(f"  intro: {SWEEP_DUR}s sweep+reverb | body: {body_end-CUT_START:.1f}s | ending: {ENDING_DUR}s delay+filter+fade")
