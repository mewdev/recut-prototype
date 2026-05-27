#!/usr/bin/env python3
"""
Extended v4 — same edit as v3 but with equal-power crossfades at cut points.

Cut points (all in E/B major zone, C#m7→C#m7):
  81.70s → 52.91s  (dev cycle 1)
  81.70s → 52.91s  (dev cycle 2)
  81.70s → outro

Crossfade: 120ms equal-power (sqrt ramp).
Short enough not to blur musical phrasing, long enough to kill the pop.
"""

import numpy as np
import librosa
import soundfile as sf

SRC  = "Building A Family (1).mp3"
OUT  = "Building A Family - extended v4.mp3"
XFADE_MS = 80  # ms

# Strategy: extend each non-final section by XFADE_MS into its decay zone,
# so the crossfade happens AFTER the downbeat (in the note tail), not ON it.
# B's downbeat lands at exactly the junction point in the output.
#
#  A: ──────────────────[beat]──decay──|
#  B:                             [beat]────────────────
#  xfade:                    ╔════════╗
#  output: ─────────────────[beat]=B's beat lands here

audio, sr = librosa.load(SRC, sr=None, mono=False)
if audio.ndim == 1:
    audio = np.stack([audio, audio])

xfade    = int(XFADE_MS / 1000 * sr)
xfade_s  = XFADE_MS / 1000  # in seconds

# Each section except the last is extended by xfade_s into its decay
edit = [
    (0,     81.70 + xfade_s, "original-through-inst"),
    (52.91, 81.70 + xfade_s, "dev-cycle-1"),
    (52.91, 81.70 + xfade_s, "dev-cycle-2"),
    (81.70, 117.4,            "coda-outro-end"),        # last — no extension
]

def to_samples(t): return int(round(t * sr))

# Extract sections
sections = []
for start, end, label in edit:
    s, e = to_samples(start), min(to_samples(end), audio.shape[1])
    sections.append(audio[:, s:e].copy())
    print(f"  {label}: {start:.3f}→{end:.3f}s  ({e-s} samples)")

# Equal-power ramps
ramp_out = np.sqrt(np.linspace(1.0, 0.0, xfade))
ramp_in  = np.sqrt(np.linspace(0.0, 1.0, xfade))

def xfade_join(a, b):
    """Crossfade: last xfade of a fades out while first xfade of b fades in."""
    out = a.copy()
    out[:, -xfade:] *= ramp_out[np.newaxis, :]
    out[:, -xfade:] += b[:, :xfade] * ramp_in[np.newaxis, :]
    return np.concatenate([out, b[:, xfade:]], axis=1)

result = sections[0]
for sec in sections[1:]:
    result = xfade_join(result, sec)

total_s = result.shape[1] / sr
print(f"\nTotal: {total_s:.1f}s = {int(total_s//60)}:{int(total_s%60):02d}")

# Write as WAV first then convert to MP3 via ffmpeg
tmp_wav = "/tmp/v4_raw.wav"
sf.write(tmp_wav, result.T, sr)

import subprocess
subprocess.run([
    "ffmpeg", "-y", "-i", tmp_wav,
    "-codec:a", "libmp3lame", "-q:a", "2", OUT
], check=True, capture_output=True)

import os
print(f"Done: {OUT}  ({os.path.getsize(OUT)/1e6:.1f} MB)")
print(f"Crossfade: {XFADE_MS}ms equal-power, placed in decay zone after each downbeat")
