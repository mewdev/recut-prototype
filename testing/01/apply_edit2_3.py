#!/usr/bin/env python3
"""
Edit 2.3: Two-layer ending — no hard join at the delay zone.

Layer 1 (dry):  full body plays uninterrupted, fades 1→0 over last ENDING_DUR
Layer 2 (wet):  delay+reverb on the ending phrase, fades 0→peak→0 (bell curve)
Both layers are mixed together and aligned in time — no xfade cut.

Output: labour-edit2.3.mp3
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
OUT          = "testing/01/labour-edit2.3.mp3"
CUT_START    = 51.15
CUT_END      = 89.01
SWEEP_DUR    = 6.0
FREQ_FLOOR   = 220.0
FREQ_CEIL    = 20000.0
CURVE        = 6.0
ENDING_DUR   = 5.0
BPM          = 83
ONE_BEAT     = 60.0 / BPM  # 0.723s

print(f"Loading {SRC}...")
audio, sr = librosa.load(SRC, sr=None, mono=False)
if audio.ndim == 1:
    audio = np.stack([audio, audio])

# ── Intro ─────────────────────────────────────────────────────────────────────
intro_src = cut(audio, sr, CUT_START - SWEEP_DUR, CUT_START)
intro = filter_sweep(intro_src, sr, direction="open", duration=SWEEP_DUR,
                     freq_floor=FREQ_FLOOR, freq_ceil=FREQ_CEIL, curve=CURVE)
intro = fade(intro, vol_start=0.0, vol_end=1.0)
intro = reverb(intro, sr, wetness=0.5, reverb_type="hall")
silence = np.zeros((intro.shape[0], int(0.08 * sr)), dtype=intro.dtype)
intro = np.concatenate([silence, intro], axis=1)

# ── Body: full cut, dry layer fades out over last ENDING_DUR ─────────────────
body_full = cut(audio, sr, CUT_START, CUT_END)
n_full    = body_full.shape[1]
n_end     = int(round(ENDING_DUR * sr))

dry_env = np.ones(n_full)
dry_env[-n_end:] = np.linspace(1.0, 0.0, n_end)
dry_layer = body_full * dry_env[np.newaxis, :]

# ── Wet layer: delay+reverb on ending phrase, bell-curve envelope ─────────────
ending_src = cut(audio, sr, CUT_END - ENDING_DUR, CUT_END)
wet = delay(ending_src, sr, delay_seconds=ONE_BEAT, feedback=0.5, wetness=1.0)
wet = reverb(wet, sr, wetness=0.4, reverb_type="hall")

# bell curve: fade in over first half, fade out over second half
bell = np.concatenate([
    np.linspace(0.0, 0.55, n_end // 2),
    np.linspace(0.55, 0.0, n_end - n_end // 2),
])
wet = wet * bell[np.newaxis, :]

# pad with silence at the front to align with the ending zone in body
pad = np.zeros((2, n_full - n_end))
wet_layer = np.concatenate([pad, wet], axis=1)

# ── Mix layers ────────────────────────────────────────────────────────────────
body_mix = dry_layer + wet_layer

# ── Join intro + body_mix ─────────────────────────────────────────────────────
result = xfade_join(intro, body_mix, xfade_ms=60, sr=sr)

tmp = tempfile.mktemp(suffix=".wav")
sf.write(tmp, result.T, sr)
subprocess.run([
    "ffmpeg", "-y", "-i", tmp,
    "-codec:a", "libmp3lame", "-q:a", "2", OUT
], check=True, capture_output=True)
os.unlink(tmp)

print(f"✓ {OUT}  ({result.shape[1]/sr:.1f}s)")
print(f"  delay: {ONE_BEAT:.3f}s ({BPM} BPM)  ending zone: {ENDING_DUR}s two-layer mix")
