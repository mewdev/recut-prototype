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
OUT   = f'{STEMS}/chicago-cut-v15.mp3'

TRIM_START       = 61.56
DRUM_CUT_ABS     = 196.68   # 2:15 — bass+vox cut, drums begin fading
DRUM_FADE_END_ABS = 207.34  # 2:25.78 — drums reach zero (2 bars early)
SWEEP_ABS        = 210.90   # 2:29 — piano exit starts
CLIP_END_ABS     = 231.00

CLIP_DUR        = CLIP_END_ABS    - TRIM_START   # 169.44s
cut_rel         = DRUM_CUT_ABS    - TRIM_START   # 135.12s
drum_fade_rel   = DRUM_FADE_END_ABS - TRIM_START # 145.78s
sweep_rel       = SWEEP_ABS       - TRIM_START   # 149.34s
sweep_dur       = CLIP_END_ABS    - SWEEP_ABS    # 20.1s

FADE_OUT_START = 14.5

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

taper_samp     = int(0.3 * sr)
fi_samp        = int(0.5 * sr)
cut_samp       = int(cut_rel       * sr)
drum_fade_samp = int(drum_fade_rel * sr)
sweep_samp     = int(sweep_rel     * sr)

# --- bass + vox: cut at 2:15 ---
for stem in (bass, vox):
    stem[:, cut_samp : cut_samp + taper_samp] *= np.linspace(1.0, 0.0, taper_samp)
    stem[:, cut_samp + taper_samp:] = 0.0

# --- drums: fade 1.0→0.0 from 2:15 to 2:25.78, silent after ---
drums[:, cut_samp:drum_fade_samp] = fade(
    drums[:, cut_samp:drum_fade_samp].copy(), sr, vol_start=1.0, vol_end=0.0
)
drums[:, drum_fade_samp:] = 0.0   # completely silent — no kicks at 2:28-2:29

# --- piano dry: full until sweep_samp, short taper ---
piano_dry = piano.copy()
piano_dry[:, sweep_samp : sweep_samp + taper_samp] *= np.linspace(1.0, 0.0, taper_samp)
piano_dry[:, sweep_samp + taper_samp:] = 0.0

# --- piano creative exit: sweep + reverb + late fade ---
piano_end = chain(
    piano[:, sweep_samp:].copy(), sr,
    (filter_sweep, dict(direction="close", duration=sweep_dur,
                        freq_ceil=8000.0, freq_floor=200.0, curve=2.5)),
    (reverb,       dict(wetness=0.38, reverb_type="hall")),
)
piano_end[:, :fi_samp] *= np.linspace(0.0, 1.0, fi_samp)
fo_start = int(FADE_OUT_START * sr)
piano_end[:, fo_start:] *= np.linspace(1.0, 0.0, piano_end.shape[1] - fo_start)

# --- build mix ---
mix = combine_stems(piano_dry, drums, bass, vox)
mix[:, sweep_samp:] += piano_end

# --- fade in at clip start ---
mix[:, :int(0.5 * sr)] = fade(mix[:, :int(0.5 * sr)], sr, vol_start=0.0, vol_end=1.0)

# --- normalise ---
peak = np.max(np.abs(mix))
if peak > 0.95:
    mix *= 0.95 / peak

print(f"Writing {OUT} ...")
with AudioFile(OUT, 'w', samplerate=sr, num_channels=mix.shape[0]) as f:
    f.write(mix)

dur = mix.shape[1] / sr
print(f"Done. Duration: {dur:.2f}s  ({int(dur//60)}:{dur%60:05.2f})")
