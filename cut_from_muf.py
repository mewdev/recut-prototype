"""
Cut end_of_beginning per screenshot arrangement using MUF sample-exact boundaries.

Arrangement: 01_int | 01_int | 03_chorus_01 | 07_bridge_01

Effects from screenshot:
  AUTOFILTER R  → filter_sweep(open) on both intros
  CROSSFADE     → xfade_join at chorus_01 → bridge_01 junction
  REVERB        → reverb on bridge_01

MUF sections (44100Hz):
  MUF[0] intro:      4085  – 136730    (0.09–3.10s)
  MUF[2] chorus_01:  1592003 – 2650252  (36.10–60.10s)
  MUF[5] bridge_01:  4833470 – 5892240  (109.60–133.61s)
          ↑ MUF boundary — 3s earlier than songformer's 112.56s
"""

import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, "primitives")
from filter_sweep import filter_sweep
from reverb import reverb

AUDIO_IN  = "mp3/end_of_beginning.mp3"
AUDIO_OUT = "output/cut_01int_01int_03chorus_07bridge.wav"

# MUF sample boundaries (44100Hz)
MUF = {
    "intro":     (4085,    136730),
    "chorus_01": (1592003, 2650252),
}

# Bridge: MUF[5] starts 3s early; use beat+chord change at 112.61s (G:maj→A:maj)
BRIDGE_START = 112.61  # seconds — sample 4965770
BRIDGE_END   = 133.61  # MUF[5] end

def cut(audio, start, end):
    return audio[:, start:end]

def main():
    audio, sr = sf.read(AUDIO_IN, always_2d=True)
    audio = audio.T.astype(np.float32)  # → (channels, samples)
    assert sr == 44100

    intro     = cut(audio, *MUF["intro"])
    chorus_01 = cut(audio, *MUF["chorus_01"])
    bridge_01 = audio[:, int(BRIDGE_START * sr):int(BRIDGE_END * sr)]

    # AUTOFILTER R: open sweep across both intros as one 6s unit
    intro_double = np.concatenate([intro, intro], axis=1)
    intro_swept = filter_sweep(intro_double, sr, direction="open", duration=intro_double.shape[1] / sr)

    # REVERB: last 2 beats (1.5s @ 80bpm) + 4s decay silence
    # Settings from Hybrid Reverb: Dark Hall, size=50%, damping=50%, dry/wet=28%
    beat_dur = 60.0 / 80.0          # 0.75s
    tail_samples = int(2 * beat_dur * sr)  # 2 beats = 1.5s
    decay_silence = np.zeros((audio.shape[0], int(4.0 * sr)), dtype=np.float32)
    bridge_body = bridge_01[:, :-tail_samples]
    bridge_tail = np.concatenate([bridge_01[:, -tail_samples:], decay_silence], axis=1)
    bridge_tail_wet = reverb(
        bridge_tail, sr,
        wetness=0.28,
        room_size=0.5,
        damping=0.5,
        width=1.0,
    )
    bridge_processed = np.concatenate([bridge_body, bridge_tail_wet], axis=1)

    # Chorus plays to completion, bridge starts clean at 1:52
    result = np.concatenate([intro_swept, chorus_01, bridge_processed], axis=1)

    import os
    os.makedirs("output", exist_ok=True)
    sf.write(AUDIO_OUT, result.T, sr)

    print(f"Written: {AUDIO_OUT}  ({result.shape[1]/sr:.1f}s)")

if __name__ == "__main__":
    main()
