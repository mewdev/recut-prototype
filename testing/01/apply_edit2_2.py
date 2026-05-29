#!/usr/bin/env python3
"""
Edit 2.2: Same intro as 2.1, but ending preserves dry audio fading out
          while delay+reverb plays underneath — no harsh cut.

Ending approach:
  dry  = original audio, fades out 1.0 → 0.0
  wet  = delay (beat-synced to 83 BPM) + reverb, lower level, fades slower
  end  = dry + wet  →  seamless dissolve into echo tail

Output: labour-edit2.2.mp3
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
OUT          = "testing/01/labour-edit2.2.mp3"
CUT_START    = 51.15
CUT_END      = 89.01
SWEEP_DUR    = 6.0
FREQ_FLOOR   = 220.0
FREQ_CEIL    = 20000.0
CURVE        = 6.0
ENDING_DUR   = 5.0
BPM          = 83
ONE_BEAT     = 60.0 / BPM   # 0.723s — delay aligned to tempo

print(f"Loading {SRC}...")
audio, sr = librosa.load(SRC, sr=None, mono=False)
if audio.ndim == 1:
    audio = np.stack([audio, audio])

# ── Intro (same as 1.5/2.1) ──────────────────────────────────────────────────
intro_src = cut(audio, sr, CUT_START - SWEEP_DUR, CUT_START)
intro = filter_sweep(intro_src, sr, direction="open", duration=SWEEP_DUR,
                     freq_floor=FREQ_FLOOR, freq_ceil=FREQ_CEIL, curve=CURVE)
intro = fade(intro, vol_start=0.0, vol_end=1.0)
intro = reverb(intro, sr, wetness=0.5, reverb_type="hall")
silence = np.zeros((intro.shape[0], int(0.08 * sr)), dtype=intro.dtype)
intro = np.concatenate([silence, intro], axis=1)

# ── Main body ────────────────────────────────────────────────────────────────
body_end = CUT_END - ENDING_DUR
body = cut(audio, sr, CUT_START, body_end)

# ── Ending: dry fades out, wet delay+reverb dissolves underneath ──────────────
ending_src = cut(audio, sr, body_end, CUT_END)

# dry — original, fades out
dry = fade(ending_src, vol_start=1.0, vol_end=0.0)

# wet — pure delay echo (wetness=1.0 = delay signal only, no dry)
# delay time = one beat at 83 BPM
wet = delay(ending_src, sr, delay_seconds=ONE_BEAT, feedback=0.5, wetness=1.0)
wet = reverb(wet, sr, wetness=0.4, reverb_type="hall")
wet = fade(wet, vol_start=0.5, vol_end=0.0)   # slightly louder start, fades out

ending = dry + wet

# ── Join ──────────────────────────────────────────────────────────────────────
mid    = xfade_join(intro, body, xfade_ms=60, sr=sr)
result = xfade_join(mid, ending, xfade_ms=80, sr=sr)

tmp = tempfile.mktemp(suffix=".wav")
sf.write(tmp, result.T, sr)
subprocess.run([
    "ffmpeg", "-y", "-i", tmp,
    "-codec:a", "libmp3lame", "-q:a", "2", OUT
], check=True, capture_output=True)
os.unlink(tmp)

print(f"✓ {OUT}  ({result.shape[1]/sr:.1f}s)")
print(f"  delay: {ONE_BEAT:.3f}s ({BPM} BPM, 1 beat)  ending: {ENDING_DUR}s")
