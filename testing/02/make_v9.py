import sys
sys.path.insert(0, '/Users/michal/Documents/dev/recut-prototype')

import numpy as np
from pedalboard.io import AudioFile

from primitives.fade          import fade
from primitives.filter_sweep  import filter_sweep
from primitives.reverb        import reverb
from primitives.chain         import chain
from primitives.combine_stems import combine_stems

STEMS = '/Users/michal/Documents/dev/recut-prototype/testing/02'
OUT   = f'{STEMS}/chicago-cut-v9.mp3'

TRIM_START   = 61.56
DRUM_CUT_ABS = 196.68   # 2:15 — ambient layer starts, drums still play
SWEEP_ABS    = 210.90   # 2:29 — all stems cut, piano-only creative exit
CLIP_END_ABS = 231.00

CLIP_DUR  = CLIP_END_ABS - TRIM_START   # 169.44s
cut_rel   = DRUM_CUT_ABS - TRIM_START   # 135.12s  (other_ambient fades in here)
sweep_rel = SWEEP_ABS    - TRIM_START   # 149.34s  (all stems cut here)
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

taper_samp  = int(0.3 * sr)
fade_in_amb = int(2.0 * sr)   # other_ambient fade-in duration
fade_out_amb = int(1.5 * sr)  # other_ambient fade-out duration

cut_samp   = int(cut_rel   * sr)
sweep_samp = int(sweep_rel * sr)

# --- all stems taper out at sweep_samp (2:29) ---
for stem in (drums, bass, vox):
    stem[:, sweep_samp : sweep_samp + taper_samp] *= np.linspace(1.0, 0.0, taper_samp)
    stem[:, sweep_samp + taper_samp:] = 0.0

# piano: unchanged before sweep, sweep+reverb+fade applied from sweep_samp
piano_dry = piano.copy()
piano_dry[:, sweep_samp + taper_samp:] = 0.0  # silence piano in the dry channel after sweep
piano_dry[:, sweep_samp : sweep_samp + taper_samp] *= np.linspace(1.0, 0.0, taper_samp)

# --- other_ambient: reverbed piano, active cut_samp → sweep_samp ---
other_ambient = reverb(piano.copy(), sr, wetness=0.7, reverb_type="hall") * 0.3
other_ambient[:, :cut_samp] = 0.0
# fade in over 2s
other_ambient[:, cut_samp : cut_samp + fade_in_amb] *= np.linspace(0.0, 1.0, fade_in_amb)
# fade out over 1.5s ending at sweep_samp
other_ambient[:, sweep_samp - fade_out_amb : sweep_samp] *= np.linspace(1.0, 0.0, fade_out_amb)
other_ambient[:, sweep_samp:] = 0.0

# --- piano creative exit: sweep + reverb + fade from sweep_samp ---
piano_end = piano[:, sweep_samp:].copy()
piano_end = chain(
    piano_end, sr,
    (filter_sweep, dict(direction="close", duration=sweep_dur,
                        freq_ceil=18000.0, freq_floor=200.0, curve=2.5)),
    (reverb,       dict(wetness=0.55, reverb_type="hall")),
    (fade,         dict(vol_start=1.0, vol_end=0.0)),
)

# --- build mix ---
mix = combine_stems(piano_dry, drums, bass, vox, other_ambient)
mix[:, sweep_samp:] += piano_end  # add piano exit on top (piano_dry is zeroed there)

# --- fade in at clip start ---
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
