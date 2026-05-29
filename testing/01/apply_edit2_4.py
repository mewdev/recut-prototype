#!/usr/bin/env python3
"""
Edit 2.4:
  Layer 1 (dry):  full body, only a short 0.4s fade at the very end
  Layer 2 (wet):  delay+reverb on ending phrase, extends PAST CUT_END
                  so the echo tail rings out naturally — no forced fade out

Output: labour-edit2.4.mp3
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
from primitives.chain import chain

SRC          = "testing/01/labour.mp3"
OUT          = "testing/01/labour-edit2.4.mp3"
CUT_START    = 51.15
CUT_END      = 89.01
SWEEP_DUR    = 6.0
FREQ_FLOOR   = 220.0
FREQ_CEIL    = 20000.0
CURVE        = 6.0
ENDING_DUR   = 5.0    # how far back the wet layer starts
TAIL_DUR     = 5.0    # extra seconds after CUT_END for delay to ring out
DRY_FADE     = 2.0    # gentle taper at end — keeps vocals, avoids harsh jump to delay-only
BPM          = 83
ONE_BEAT     = 60.0 / BPM  # 0.723s

print(f"Loading {SRC}...")
audio, sr = librosa.load(SRC, sr=None, mono=False)
if audio.ndim == 1:
    audio = np.stack([audio, audio])

# ── Intro ─────────────────────────────────────────────────────────────────────
intro_src = cut(audio, sr, CUT_START - SWEEP_DUR, CUT_START)
intro = chain(intro_src, sr,
    (filter_sweep, dict(direction="open", duration=SWEEP_DUR,
                        freq_floor=FREQ_FLOOR, freq_ceil=FREQ_CEIL, curve=CURVE)),
    (fade,         dict(vol_start=0.0, vol_end=1.0)),
    (reverb,       dict(wetness=0.5, reverb_type="hall")),
)
silence = np.zeros((intro.shape[0], int(0.08 * sr)), dtype=intro.dtype)
intro = np.concatenate([silence, intro], axis=1)

# ── Layer 1: dry — full body, very short fade at the end ─────────────────────
body_full = cut(audio, sr, CUT_START, CUT_END)
n_full    = body_full.shape[1]
n_fade    = int(round(DRY_FADE * sr))
dry_env   = np.ones(n_full)
dry_env[-n_fade:] = np.linspace(1.0, 0.0, n_fade)
dry_layer = body_full * dry_env[np.newaxis, :]

# ── Layer 2: wet — delay+reverb, extends past CUT_END for natural tail ────────
ending_src = cut(audio, sr, CUT_END - ENDING_DUR, CUT_END)

# micro-fades on ending_src: eliminate discontinuity at both boundaries
micro_n = int(round(0.010 * sr))  # 10ms
ending_src[:, :micro_n]  *= np.linspace(0.0, 1.0, micro_n)[np.newaxis, :]  # fade in
ending_src[:, -micro_n:] *= np.linspace(1.0, 0.0, micro_n)[np.newaxis, :]  # fade out

# append silence so delay tail can ring out naturally after source ends
tail_silence = np.zeros((2, int(round(TAIL_DUR * sr))), dtype=ending_src.dtype)
ending_with_tail = np.concatenate([ending_src, tail_silence], axis=1)

# warmup must exceed one full delay cycle so buffer is settled before audio starts
WARMUP_DUR = ONE_BEAT + 0.5   # ~1.22s — well beyond one delay cycle
warmup = np.zeros((2, int(round(WARMUP_DUR * sr))), dtype=ending_with_tail.dtype)
ending_padded = np.concatenate([warmup, ending_with_tail], axis=1)
wet = chain(ending_padded, sr,
    (delay,  dict(delay_seconds=ONE_BEAT, feedback=0.5, wetness=1.0)),
    (reverb, dict(wetness=0.35, reverb_type="hall")),
)
wet = wet[:, warmup.shape[1]:]  # trim the warmup silence back off

# wet envelope: fade in over 2s, hold during source audio, fade out over tail
n_wet      = wet.shape[1]
n_fade_in  = int(round(2.0 * sr))
n_source   = int(round(ENDING_DUR * sr))   # 5s — where source audio ends, tail begins
n_tail     = n_wet - n_source               # remainder is just delay/reverb decay
wet_env    = np.ones(n_wet)
wet_env[:n_fade_in]        = np.linspace(0.0, 0.2, n_fade_in)
wet_env[n_fade_in:n_source] = 0.2
wet_env[n_source:]          = np.linspace(0.2, 0.0, n_tail)   # fade out the tail
wet = wet * wet_env[np.newaxis, :]

# ── Align layers: pad dry to match total length ───────────────────────────────
n_wet_total = wet.shape[1]
n_offset    = n_full - int(round(ENDING_DUR * sr))   # where wet starts in body

# build full-length dry (padded with silence after CUT_END)
dry_padded = np.concatenate([dry_layer, np.zeros((2, n_wet_total - n_offset - int(round(ENDING_DUR * sr))))], axis=1) if n_wet_total > n_full else dry_layer
# simpler: pad dry with zeros to match wet start offset + wet length
pad_before_wet = np.zeros((2, n_offset), dtype=wet.dtype)
wet_aligned    = np.concatenate([pad_before_wet, wet], axis=1)

# match lengths
total = max(dry_layer.shape[1], wet_aligned.shape[1])
def pad_to(a, n): return np.concatenate([a, np.zeros((2, n - a.shape[1]), dtype=a.dtype)], axis=1)
dry_f = pad_to(dry_layer, total)
wet_f = pad_to(wet_aligned, total)

body_mix = dry_f + wet_f

# ── Join ──────────────────────────────────────────────────────────────────────
result = xfade_join(intro, body_mix, xfade_ms=60, sr=sr)

tmp = tempfile.mktemp(suffix=".wav")
sf.write(tmp, result.T, sr)
subprocess.run([
    "ffmpeg", "-y", "-i", tmp,
    "-codec:a", "libmp3lame", "-q:a", "2", OUT
], check=True, capture_output=True)
os.unlink(tmp)

print(f"✓ {OUT}  ({result.shape[1]/sr:.1f}s)")
print(f"  dry fade: {DRY_FADE}s  |  delay tail: +{TAIL_DUR}s past cut end")
