import sys
sys.path.insert(0, '/Users/michal/Documents/dev/recut-prototype')

import numpy as np
from pedalboard.io import AudioFile

from primitives.fade          import fade
from primitives.eq            import eq
from primitives.filter_sweep  import filter_sweep
from primitives.reverb        import reverb
from primitives.chain         import chain
from primitives.combine_stems import combine_stems

STEMS = '/Users/michal/Documents/dev/recut-prototype/testing/02'
OUT   = f'{STEMS}/chicago-cut-v8.mp3'

TRIM_START   = 61.56
DRUM_CUT_ABS = 196.68
SWEEP_ABS    = 210.90
CLIP_END_ABS = 231.00

CLIP_DUR   = CLIP_END_ABS - TRIM_START   # 169.44s
cut_rel    = DRUM_CUT_ABS - TRIM_START   # 135.12s
sweep_rel  = SWEEP_ABS    - TRIM_START   # 149.34s
sweep_dur  = CLIP_DUR     - cut_rel      # 34.32s — piano sweep covers cut→end

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

taper_samp  = int(0.3  * sr)
taper_long  = int(1.5  * sr)
taper_short = int(0.5  * sr)
cut_samp    = int(cut_rel   * sr)
sweep_samp  = int(sweep_rel * sr)

# --- bass + vox: taper out at cut_samp ---
for stem in (bass, vox):
    stem[:, cut_samp : cut_samp + taper_samp] *= np.linspace(1.0, 0.0, taper_samp)
    stem[:, cut_samp + taper_samp:] = 0.0

# --- drums_dry: taper out at cut_samp ---
drums_dry = drums.copy()
drums_dry[:, cut_samp : cut_samp + taper_samp] *= np.linspace(1.0, 0.0, taper_samp)
drums_dry[:, cut_samp + taper_samp:] = 0.0

# --- drums_rev: eq(400Hz high) → reverb(0.85 wet hall), active cut→sweep ---
drums_rev = chain(
    drums, sr,
    (eq,     dict(cutoff=400, type="high")),
    (reverb, dict(wetness=0.85, reverb_type="hall")),
)
drums_rev[:, :cut_samp] = 0.0
drums_rev[:, cut_samp : cut_samp + taper_samp] *= np.linspace(0.0, 1.0, taper_samp)
# taper out 1.5s before sweep_samp
drums_rev[:, sweep_samp - taper_long : sweep_samp] *= np.linspace(1.0, 0.0, taper_long)
drums_rev[:, sweep_samp:] = 0.0

# --- other_ambient: reverb(0.75 wet hall) × 0.35, active cut→sweep ---
other_ambient = reverb(piano.copy(), sr, wetness=0.75, reverb_type="hall") * 0.35
other_ambient[:, :cut_samp] = 0.0
other_ambient[:, cut_samp : cut_samp + taper_short] *= np.linspace(0.0, 1.0, taper_short)
other_ambient[:, sweep_samp - taper_long : sweep_samp] *= np.linspace(1.0, 0.0, taper_long)
other_ambient[:, sweep_samp:] = 0.0

# --- piano: apply long transparent sweep from cut_samp to end ---
# curve=2.5 keeps filter near 20kHz for most of the section, drops fast at the end
# at 2:29 (14s into 34s sweep) cutoff ≈ 12kHz — perceptually transparent
piano_out = piano.copy()
piano_out[:, cut_samp:] = filter_sweep(
    piano[:, cut_samp:], sr,
    direction="close",
    duration=sweep_dur,
    freq_ceil=20000.0,
    freq_floor=200.0,
    curve=2.5,
)

# add hall reverb to piano from sweep_samp onwards
piano_out[:, sweep_samp:] = reverb(
    piano_out[:, sweep_samp:], sr,
    wetness=0.55, reverb_type="hall",
)

# fade out piano over the full sweep section (cut_samp → end)
piano_out[:, cut_samp:] = fade(piano_out[:, cut_samp:], sr, vol_start=1.0, vol_end=0.0)

# --- single continuous mix ---
mix = combine_stems(piano_out, bass, vox, drums_dry, drums_rev, other_ambient)

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
