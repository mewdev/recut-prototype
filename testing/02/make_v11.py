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
OUT   = f'{STEMS}/chicago-cut-v11.mp3'

TRIM_START   = 61.56
DRUM_CUT_ABS = 196.68   # 2:15 — bass + vox cut, other_ambient fades in
SWEEP_ABS    = 210.90   # 2:29 — drums crossfade out, piano_end crossfades in
CLIP_END_ABS = 231.00

CLIP_DUR  = CLIP_END_ABS - TRIM_START   # 169.44s
cut_rel   = DRUM_CUT_ABS - TRIM_START   # 135.12s
sweep_rel = SWEEP_ABS    - TRIM_START   # 149.34s
sweep_dur = CLIP_END_ABS - SWEEP_ABS    # 20.1s

FADE_OUT_START_REL = 14.5  # seconds into piano_end where fade begins (~2:44)
FADE_OUT_DUR       = sweep_dur - FADE_OUT_START_REL  # ~5.6s

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

taper_short  = int(0.3 * sr)
xfade_dur    = int(1.5 * sr)   # crossfade duration at 2:29
fade_in_amb  = int(2.0 * sr)
fade_out_amb = int(1.5 * sr)

cut_samp   = int(cut_rel   * sr)
sweep_samp = int(sweep_rel * sr)

# --- bass + vox: cut at 2:15 ---
for stem in (bass, vox):
    stem[:, cut_samp : cut_samp + taper_short] *= np.linspace(1.0, 0.0, taper_short)
    stem[:, cut_samp + taper_short:] = 0.0

# --- drums: longer 1.5s taper at 2:29 ---
drums[:, sweep_samp : sweep_samp + xfade_dur] *= np.linspace(1.0, 0.0, xfade_dur)
drums[:, sweep_samp + xfade_dur:] = 0.0

# --- other_ambient: strings/cello — no EQ, very light room reverb ---
other_ambient = reverb(piano.copy(), sr, wetness=0.12, reverb_type="room") * 0.2
other_ambient[:, :cut_samp] = 0.0
other_ambient[:, cut_samp : cut_samp + fade_in_amb] *= np.linspace(0.0, 1.0, fade_in_amb)
other_ambient[:, sweep_samp - fade_out_amb : sweep_samp] *= np.linspace(1.0, 0.0, fade_out_amb)
other_ambient[:, sweep_samp:] = 0.0

# --- piano dry: taper at 2:29 ---
piano_dry = piano.copy()
piano_dry[:, sweep_samp : sweep_samp + taper_short] *= np.linspace(1.0, 0.0, taper_short)
piano_dry[:, sweep_samp + taper_short:] = 0.0

# --- piano creative exit: sweep + reverb, then late fade ---
piano_end = chain(
    piano[:, sweep_samp:].copy(), sr,
    (filter_sweep, dict(direction="close", duration=sweep_dur,
                        freq_ceil=8000.0, freq_floor=200.0, curve=2.5)),
    (reverb,       dict(wetness=0.55, reverb_type="hall")),
)

# fade IN over 1.5s (crossfades with drums fading out)
piano_end[:, :xfade_dur] *= np.linspace(0.0, 1.0, xfade_dur)

# fade OUT only in the last ~5.6s (from 2:44)
fo_start = int(FADE_OUT_START_REL * sr)
piano_end[:, fo_start:] *= np.linspace(1.0, 0.0, piano_end.shape[1] - fo_start)

# --- build mix ---
mix = combine_stems(piano_dry, drums, bass, vox, other_ambient)
mix[:, sweep_samp:] += piano_end

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
