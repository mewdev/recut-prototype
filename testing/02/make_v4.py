import sys
sys.path.insert(0, '/Users/michal/Documents/dev/recut-prototype')

import numpy as np
from pedalboard.io import AudioFile

from primitives.cut           import cut
from primitives.fade          import fade
from primitives.filter_sweep  import filter_sweep
from primitives.reverb        import reverb
from primitives.chain         import chain
from primitives.xfade         import xfade_join
from primitives.combine_stems import combine_stems

STEMS   = '/Users/michal/Documents/dev/recut-prototype/testing/02'
OUT     = f'{STEMS}/chicago-cut-v4.mp3'

# --- absolute timestamps (original file) ---
TRIM_START   = 61.56   # new clip start
DRUM_CUT_ABS = 196.68  # phrase A repeat downbeat — drum cut
SWEEP_ABS    = 210.90  # chorus — creative exit begins
CLIP_END_ABS = 231.00  # ~2:49 in clip

CLIP_DUR = CLIP_END_ABS - TRIM_START  # 169.44s

# --- relative timestamps (within loaded segment) ---
cut_rel   = DRUM_CUT_ABS - TRIM_START  # 135.12s
sweep_rel = SWEEP_ABS    - TRIM_START  # 149.34s
sweep_dur = CLIP_END_ABS - SWEEP_ABS   # 20.1s

def load(path):
    with AudioFile(path) as f:
        sr = f.samplerate
        f.seek(int(TRIM_START * sr))
        audio = f.read(int(CLIP_DUR * sr))
    return audio, sr

print("Loading stems...")
drums, sr = load(f'{STEMS}/drums.wav')
bass,  _  = load(f'{STEMS}/bass.wav')
piano, _  = load(f'{STEMS}/other.wav')
vox,   _  = load(f'{STEMS}/vocals.wav')

# --- phrase A (0 → cut_rel): full band ---
# --- phrase A repeat (cut_rel → end): piano only ---
# Hard-cut drums/bass/vox at downbeat; short fade on the cut tail to kill transient
drums_a = cut(drums, sr, 0, cut_rel)
bass_a  = cut(bass,  sr, 0, cut_rel)
vox_a   = cut(vox,   sr, 0, cut_rel)
piano_a = cut(piano, sr, 0, cut_rel)

# 0.3s fade-out taper at the cut point (avoids click, not audible as a fade)
taper_dur = 0.3
drums_a = chain(drums_a, sr, (fade, dict(vol_start=1.0, vol_end=1.0)))  # full — tail taper below
taper_samp = int(taper_dur * sr)
for stem in (drums_a, bass_a, vox_a):
    stem[:, -taper_samp:] *= np.linspace(1.0, 0.0, taper_samp)

full_section = combine_stems(drums_a, bass_a, piano_a, vox_a)

piano_b = cut(piano, sr, cut_rel, CLIP_DUR)

# --- creative exit: sweep + reverb on the chorus section (sweep_rel → end) ---
sweep_start_rel = sweep_rel - cut_rel  # relative within piano_b
piano_b_pre   = cut(piano_b, sr, 0, sweep_start_rel)
piano_b_sweep = cut(piano_b, sr, sweep_start_rel, piano_b.shape[1] / sr)

piano_b_sweep = chain(
    piano_b_sweep, sr,
    (filter_sweep, dict(direction="close", duration=sweep_dur,
                        freq_floor=200.0, freq_ceil=8000.0, curve=0.6)),
    (reverb,       dict(wetness=0.55, reverb_type="hall")),
    (fade,         dict(vol_start=1.0, vol_end=0.0)),  # fade out over whole sweep section
)

piano_b_out = np.concatenate([piano_b_pre, piano_b_sweep], axis=1)

# --- join full_section + piano_b with short xfade (300ms) ---
mix = xfade_join(full_section, piano_b_out, xfade_ms=300, sr=sr)

# --- fade in at clip start (0.5s) ---
fi = int(0.5 * sr)
mix[:, :fi] = fade(mix[:, :fi], sr, vol_start=0.0, vol_end=1.0)

# --- normalise ---
peak = np.max(np.abs(mix))
if peak > 0.95:
    mix *= 0.95 / peak

print(f"Writing {OUT} ...")
with AudioFile(OUT, 'w', samplerate=sr, num_channels=mix.shape[0]) as f:
    f.write(mix)

dur = mix.shape[1] / sr
print(f"Done. Duration: {dur:.2f}s  ({int(dur//60)}:{dur%60:05.2f})")
