#!/usr/bin/env python3
"""
Edit 1.3: Filter sweep that extends into the main cut.
          - Intro (6s before cut): 60Hz → ~6kHz  (highs just arriving at cut point)
          - Main cut head (3s):    6kHz → 20kHz  (bass fills in after cut)
          - Rest of main cut: unfiltered

Output: labour-edit1.3.mp3
"""

import sys, subprocess, tempfile, os
import numpy as np
import librosa
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from primitives.cut import cut
from primitives.filter_sweep import filter_sweep

SRC          = "testing/01/labour.mp3"
OUT          = "testing/01/labour-edit1.3.mp3"
CUT_START    = 51.15
CUT_END      = 89.01
INTRO_DUR    = 6.0    # seconds before cut — sweeps 60Hz → 6kHz
TAIL_DUR     = 3.0    # seconds into cut  — sweeps 6kHz → 20kHz
FREQ_START   = 60.0
FREQ_MID     = 6000.0  # frequency at the cut point — highs just opening
FREQ_END     = 20000.0

print(f"Loading {SRC}...")
audio, sr = librosa.load(SRC, sr=None, mono=False)
if audio.ndim == 1:
    audio = np.stack([audio, audio])

# 1. Intro sweep: audio before cut, 60Hz → 6kHz
intro_src = cut(audio, sr, CUT_START - INTRO_DUR, CUT_START)
intro = filter_sweep(intro_src, sr, duration=INTRO_DUR, freq_start=FREQ_START, freq_end=FREQ_MID)

# 2. Main cut head sweep: first 3s of cut, 6kHz → 20kHz (no volume fade, already audible)
main_src = cut(audio, sr, CUT_START, CUT_END)
tail_src = cut(audio, sr, CUT_START, CUT_START + TAIL_DUR)
tail = filter_sweep(tail_src, sr, duration=TAIL_DUR, freq_start=FREQ_MID, freq_end=FREQ_END)
# override the volume fade — tail should start at full volume (cut already happened)
fade = np.linspace(1.0, 1.0, int(round(TAIL_DUR * sr)))[np.newaxis, :]
tail = tail / np.linspace(0.0, 1.0, tail.shape[1])[np.newaxis, :].clip(0.01) * 1.0

# simpler: just apply filter without fade for the tail
from scipy.signal import butter, sosfilt, sosfilt_zi
def lpf_fixed(seg, sr, freq):
    nyq = sr / 2.0
    sos = butter(2, min(freq, nyq * 0.98) / nyq, btype="low", output="sos")
    return sosfilt(sos, seg, axis=-1)

# tail: linearly blend from lpf at FREQ_MID to unfiltered over TAIL_DUR
tail_filtered = lpf_fixed(tail_src, sr, FREQ_MID)
tail_open     = tail_src
t = np.linspace(0.0, 1.0, tail_src.shape[1])[np.newaxis, :]
tail = tail_filtered * (1 - t) + tail_open * t

# 3. Rest of main cut (after tail) — unfiltered
n_tail = int(round(TAIL_DUR * sr))
main_rest = main_src[:, n_tail:]

# 4. Join all
result = np.concatenate([intro, tail, main_rest], axis=1)

tmp = tempfile.mktemp(suffix=".wav")
sf.write(tmp, result.T, sr)
subprocess.run([
    "ffmpeg", "-y", "-i", tmp,
    "-codec:a", "libmp3lame", "-q:a", "2", OUT
], check=True, capture_output=True)
os.unlink(tmp)

print(f"✓ {OUT}  ({result.shape[1]/sr:.1f}s)")
print(f"  intro: {INTRO_DUR}s ({FREQ_START}Hz→{FREQ_MID}Hz)  tail: {TAIL_DUR}s ({FREQ_MID}Hz→{FREQ_END}Hz)")
