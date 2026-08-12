# Analysis Models

These directories are bundled into Modal container images at deploy time via `add_local_dir()`.
No manual downloads required — everything needed for `modal deploy` is already here.

## chord-cnn-lstm/
Chord recognition model (Chord-CNN-LSTM ensemble, 5 models).
- **Source:** https://github.com/ptnghia-j/chord-cnn-lstm-model
- **Contains:** inference code + trained weights (`data/*.pkl`)
- **Used by:** `run_chords()` in pipeline.py → mounted at `/chord_model` in container

## songformer/
Song structure segmentation inference code (SongFormer).
- **Source:** https://github.com/ptnghia-j/ChordMiniApp (SongFormer subdirectory)
- **Contains:** inference code only (`app.py`, `sequential_inference.py`, `src/`)
- **Used by:** `run_structure()` in pipeline.py → mounted at `/songformer` in container
- **Weights** (not stored here — downloaded automatically at image build):
  - MuQ → `OpenMuQ/MuQ-large-msd-iter` on HuggingFace
  - MusicFM → `minzwon/MusicFM` on HuggingFace
  - SongFormer checkpoint → GitHub LFS (ptnghia-j/ChordMiniApp)

## Beats (no local files)
Beat tracking via madmom — installed from GitHub at image build time.
- **Source:** https://github.com/CPJKU/madmom
