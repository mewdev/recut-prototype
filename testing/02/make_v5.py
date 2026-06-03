import sys
sys.path.insert(0, '/Users/michal/Documents/dev/recut-prototype')

import numpy as np
from pedalboard.io import AudioFile

from primitives.cut           import cut
from primitives.fade          import fade
from primitives.filter_sweep  import filter_sweep
from primitives.reverb        import reverb
from primitives.chain         import chain
from primitives.combine_stems import combine_stems

STEMS = '/Users/michal/Documents/dev/recut-prototype/testing/02'
OUT   = f'{STEMS}/chicago-cut-v5.mp3'

TRIM_START   = 61.56
DRUM_CUT_ABS = 196.68   # phrase A repeat downbeat
SWEEP_ABS    = 210.90   # chorus — creative exit
CLIP_END_ABS = 231.00

CLIP_DUR  = CLIP_END_ABS - TRIM_START   # 169.44s
cut_rel   = DRUM_CUT_ABS - TRIM_START   # 135.12s
sweep_rel = SWEEP_ABS    - TRIM_START   # 149.34s
sweep_dur = CLIP_END_ABS - SWEEP_ABS    # 20.1s

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

taper_samp = int(0.3 * sr)
cut_samp   = int(cut_rel * sr)

# --- bass + vox: taper out at cut point, silent after ---
for stem in (bass, vox):
    stem[:, cut_samp : cut_samp + taper_samp] *= np.linspace(1.0, 0.0, taper_samp)
    stem[:, cut_samp + taper_samp:] = 0.0

# --- drums_dry: same taper out ---
drums_dry = drums.copy()
drums_dry[:, cut_samp : cut_samp + taper_samp] *= np.linspace(1.0, 0.0, taper_samp)
drums_dry[:, cut_samp + taper_samp:] = 0.0

# --- drums_reverb: full reverb stem, fades IN at cut point, silent before ---
drums_rev = reverb(drums, sr, wetness=0.85, reverb_type="hall")
drums_rev[:, :cut_samp] = 0.0
drums_rev[:, cut_samp : cut_samp + taper_samp] *= np.linspace(0.0, 1.0, taper_samp)

# --- continuous mix over single timeline ---
mix = combine_stems(piano, bass, vox, drums_dry, drums_rev)

# --- creative exit: apply sweep + reverb + fade to chorus section ---
sweep_samp = int(sweep_rel * sr)
sweep_seg  = mix[:, sweep_samp:].copy()

sweep_seg = chain(
    sweep_seg, sr,
    (filter_sweep, dict(direction="close", duration=sweep_dur,
                        freq_floor=200.0, freq_ceil=8000.0, curve=0.6)),
    (reverb,       dict(wetness=0.55, reverb_type="hall")),
    (fade,         dict(vol_start=1.0, vol_end=0.0)),
)
mix[:, sweep_samp:] = sweep_seg

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
