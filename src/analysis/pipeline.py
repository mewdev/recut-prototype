"""
Full ChordMiniApp analysis pipeline on Modal

Replicates what chordmini.me does when you upload a track:
  1. Beats    — madmom (RNN + DBN beat tracking)
  2. Chords   — Chord-CNN-LSTM (5-model ensemble → .lab → JSON)
  3. Structure — SongFormer (MuQ + MusicFM embeddings → section labels)
  4. Key      — Essentia (KeyExtractor: HPCP + key-profile correlation)

All four run in parallel Modal containers, then merge into one JSON.

Usage:
    modal deploy modal_chordmini.py

    # Run full pipeline — saves <stem>-chordmini.json next to the audio
    modal run modal_chordmini.py --path path/to/track.mp3

    # Chord vocabulary: full (default), ismir2017, submission, extended
    modal run modal_chordmini.py --path track.mp3 --chord-dict submission

Output: <stem>-chordmini.json
    {
      "path": "track.mp3",
      "bpm": 117.5,
      "beats_per_bar": 4,
      "beats": [0.51, 1.02, ...],
      "downbeats": [0.51, 2.55, ...],
      "segments": [{"start": "0.0", "end": "12.5", "label": "intro"}, ...],
      "chords": [{"start": 0.0, "end": 2.3, "chord": "F#:min", "confidence": 1.0}, ...],
      "key": "F# minor",
      "_sources": {
        "beats": "madmom", "chords": "chord-cnn-lstm (full)",
        "structure": "songformer", "key": "essentia-key-extractor"
      }
    }
"""

import json
import pathlib

import modal

app = modal.App("recut-analysis")

# ── Model licensing ────────────────────────────────────────────────────────────
# ChordMini   MIT        — commercial OK
# SongFormer  MIT        — commercial OK
# MusicFM     MIT        — commercial OK
# MuQ         CC BY-NC 4.0 — NON-COMMERCIAL ONLY (Tencent AI Lab)
#   SongFormer uses MuQ as encoder → structure pipeline is non-commercial.
#   Before shipping commercially: replace MuQ or obtain a commercial license.
#   Alternatives: MERT (MIT), EnCodec (MIT)

# ── Model sources (cloned at image build time, cached by Modal) ────────────────
_CHORD_REPO = "https://github.com/ptnghia-j/chord-cnn-lstm-model"
_SONGFORMER_REPO = "https://github.com/mewdev/ChordMiniApp"

# ── Images ─────────────────────────────────────────────────────────────────────
_base = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "libsndfile1", "libfftw3-dev", "build-essential")
    .pip_install(
        "torch==2.2.2",
        extra_index_url="https://download.pytorch.org/whl/cpu",
    )
    .pip_install(
        "numpy==1.25.0",
        "librosa==0.11.0",
        "soundfile==0.13.1",
        "scipy==1.15.2",
    )
)

beats_image = (
    _base.apt_install("git")
    .pip_install("setuptools<81")  # madmom needs pkg_resources from setuptools
    .run_commands("pip install git+https://github.com/CPJKU/madmom")
)

key_image = _base.pip_install("essentia==2.1b6.dev1389")

chords_image = (
    _base.apt_install("git", "git-lfs")
    .pip_install(
        "h5py>=2.9.0",
        "mir_eval>=0.5",
        "pydub>=0.23.1",
        "jams>=0.3.4",
        "pumpp>=0.5.0",
        "scikit-learn>=0.23.2",
        "pretty_midi>=0.2.9",
        "joblib>=0.13.2",
    )
    .run_commands(
        "git lfs install",
        f"git clone {_CHORD_REPO} /chord_model",
        "git -C /chord_model lfs pull",
    )
)

_base_cuda = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "libsndfile1", "libfftw3-dev", "build-essential")
    .pip_install(
        "torch==2.2.2",
        "torchaudio==2.2.2",
        "torchvision==0.17.2",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .pip_install(
        "numpy==1.25.0",
        "librosa==0.11.0",
        "soundfile==0.13.1",
        "scipy==1.15.2",
    )
)

structure_image = (
    _base_cuda.pip_install(
        "numba==0.60.0",
        "llvmlite==0.43.0",
        "safetensors==0.5.3",
        "ema-pytorch==0.7.7",
        "omegaconf==2.3.0",
        "einops==0.8.1",
        "x-transformers==2.4.14",
        "x-clip==0.14.4",
        "easydict==1.13",
        "transformers==4.51.1",
        "huggingface-hub==0.30.1",
        "requests>=2.28.0",
        "flask>=3.0",
        "flask-cors>=4.0",
    )
    .apt_install("git", "git-lfs")
    .run_commands(
        # sparse-clone only SongFormer/ subfolder from ChordMiniApp (skip LFS — weights downloaded separately)
        "GIT_LFS_SKIP_SMUDGE=1 git clone --no-checkout --depth 1 --filter=blob:none "
        f"{_SONGFORMER_REPO} /tmp/chordminiapp",
        "git -C /tmp/chordminiapp sparse-checkout init --cone",
        "git -C /tmp/chordminiapp sparse-checkout set SongFormer",
        "GIT_LFS_SKIP_SMUDGE=1 git -C /tmp/chordminiapp checkout",
        "mv /tmp/chordminiapp/SongFormer /songformer",
    )
    # MuQ and MusicFM weights — download from HuggingFace at image build time.
    .run_commands(
        'python -c "'
        "from huggingface_hub import hf_hub_download; "
        "import shutil; "
        "src = hf_hub_download('OpenMuQ/MuQ-large-msd-iter', 'model.safetensors'); "
        "shutil.copy(src, '/songformer/src/SongFormer/ckpts/MuQ/model.safetensors'); "
        "print('MuQ weights downloaded OK')"
        '"'
    )
    .run_commands(
        'python -c "'
        "from huggingface_hub import hf_hub_download; "
        "import shutil; "
        "src = hf_hub_download('minzwon/MusicFM', 'pretrained_msd.pt'); "
        "shutil.copy(src, '/songformer/src/SongFormer/ckpts/MusicFM/pretrained_msd.pt'); "
        "print('MusicFM weights downloaded OK')"
        '"'
    )
    .run_commands(
        'python -c "'
        "import requests, pathlib, shutil; "
        "url = 'https://media.githubusercontent.com/media/mewdev/ChordMiniApp/main/SongFormer/src/SongFormer/ckpts/SongFormer.safetensors'; "
        "out = pathlib.Path('/songformer/src/SongFormer/ckpts/SongFormer.safetensors'); "
        "r = requests.get(url, stream=True); r.raise_for_status(); "
        "out.write_bytes(r.content); "
        "print('SongFormer checkpoint downloaded OK')"
        '"'
    )
)


# ── 1. Beat detection ──────────────────────────────────────────────────────────
@app.function(image=beats_image, timeout=300, memory=4096)
def run_beats(audio_bytes: bytes, filename: str = "track.mp3") -> dict:
    """madmom RNN beat tracking → beats, downbeats, bpm."""
    import tempfile
    import time

    import numpy as np

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = pathlib.Path(tmp) / filename
        audio_path.write_bytes(audio_bytes)

        t0 = time.time()
        from madmom.features.downbeats import DBNDownBeatTrackingProcessor, RNNDownBeatProcessor
        from madmom.features.tempo import TempoEstimationProcessor

        activation = RNNDownBeatProcessor()(str(audio_path))
        # joint beat+downbeat DBN — tests beats_per_bar hypotheses, picks best fit
        result = DBNDownBeatTrackingProcessor(beats_per_bar=[3, 4], fps=100)(activation)

        beat_times = result[:, 0] if len(result) else np.array([])
        downbeats = result[result[:, 1] == 1][:, 0] if len(result) else np.array([])
        beats_per_bar = int(result[:, 1].max()) if len(result) else 4

        # activation[:, 0] is the beat-activation column — reuse it for madmom's
        # own tempo estimator instead of deriving bpm from beat-interval spacing.
        tempi = TempoEstimationProcessor(fps=100)(activation[:, 0])
        bpm = float(tempi[0, 0]) if len(tempi) else 120.0

        elapsed = round(time.time() - t0, 2)
        print(f"madmom: {len(beat_times)} beats  bpm={bpm:.1f}  beats_per_bar={beats_per_bar}  {elapsed}s")

        return {
            "beats": [round(float(b), 3) for b in beat_times],
            "downbeats": [round(float(b), 3) for b in downbeats],
            "bpm": round(bpm, 2),
            "beats_per_bar": beats_per_bar,
            "model": "madmom",
        }


# ── 1b. Key detection ──────────────────────────────────────────────────────────
@app.function(image=key_image, timeout=180, memory=4096)
def run_key(audio_bytes: bytes, filename: str = "track.mp3") -> dict:
    """Essentia KeyExtractor (HPCP + key-profile correlation) → global key label (e.g. "F major")."""
    import tempfile
    import time

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = pathlib.Path(tmp) / filename
        audio_path.write_bytes(audio_bytes)

        t0 = time.time()
        import essentia.standard as es

        audio = es.MonoLoader(filename=str(audio_path))()
        tonic, scale, strength = es.KeyExtractor()(audio)
        key = f"{tonic} {scale}"

        elapsed = round(time.time() - t0, 2)
        print(f"essentia: key={key}  strength={strength:.3f}  {elapsed}s")

        return {"key": key, "strength": round(float(strength), 3), "model": "essentia-key-extractor"}


# ── 2. Chord recognition ───────────────────────────────────────────────────────
@app.function(image=chords_image, timeout=600, memory=4096)
def run_chords(audio_bytes: bytes, filename: str = "track.mp3", chord_dict: str = "full") -> dict:
    """Chord-CNN-LSTM ensemble → chord list with start/end/chord."""
    import os
    import sys
    import tempfile
    import time

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = pathlib.Path(tmp) / filename
        audio_path.write_bytes(audio_bytes)
        lab_path = pathlib.Path(tmp) / "chords.lab"

        sys.path.insert(0, "/chord_model")
        os.chdir("/chord_model")

        t0 = time.time()
        from chord_recognition import chord_recognition

        if not chord_recognition(str(audio_path), str(lab_path), chord_dict):
            raise RuntimeError("chord_recognition() returned False")

        chords = []
        with open(lab_path) as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    chords.append(
                        {
                            "start": round(float(parts[0]), 3),
                            "end": round(float(parts[1]), 3),
                            "chord": parts[2],
                        }
                    )

        elapsed = round(time.time() - t0, 2)
        print(f"chord-cnn-lstm: {len(chords)} chords  dict={chord_dict}  {elapsed}s")

        return {
            "chords": chords,
            "total_chords": len(chords),
            "duration": chords[-1]["end"] if chords else 0.0,
            "chord_dict": chord_dict,
            "model": "chord-cnn-lstm",
        }


# ── 3. Structure segmentation ──────────────────────────────────────────────────
@app.function(image=structure_image, gpu="T4", timeout=300, memory=12288)
def run_structure(audio_bytes: bytes, filename: str = "track.mp3") -> dict:
    """SongFormer (MuQ + MusicFM) → section segments with labels."""
    import importlib.util
    import sys
    import tempfile
    import time

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = pathlib.Path(tmp) / filename
        audio_path.write_bytes(audio_bytes)

        songformer_root = pathlib.Path("/songformer")
        app_path = songformer_root / "app.py"

        # app.py imports sequential_inference from its own directory at module level,
        # so /songformer must be on sys.path before exec_module runs.
        sys.path.insert(0, str(songformer_root))

        spec = importlib.util.spec_from_file_location("songformer_app", str(app_path))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load spec from {app_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["songformer_app"] = module
        # app.py does os.chdir(SONGFORMER_SRC_DIR) at module level — that's fine,
        # all model file paths inside it are relative to that dir.
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        t0 = time.time()
        module.initialize_models()

        msa_output = module.process_audio(str(audio_path))
        cleaned = module.rule_post_processing(msa_output)
        segments = module.format_as_segments(cleaned)

        elapsed = round(time.time() - t0, 2)
        print(f"songformer: {len(segments)} segments  {elapsed}s")

        # convert start/end strings → floats for consistency
        for seg in segments:
            seg["start"] = float(seg["start"])
            seg["end"] = float(seg["end"])

        return {
            "segments": segments,
            "model": "songformer",
        }


# ── Orchestrator: run all four in parallel ─────────────────────────────────────
@app.function(image=_base, timeout=1200)
def analyze_all(audio_bytes: bytes, filename: str = "track.mp3", chord_dict: str = "full") -> dict:
    """Spawn beats + chords + structure + key in parallel, merge into one JSON."""
    # spawn = fire-and-forget; returns a handle we .get() later
    beats_call = run_beats.spawn(audio_bytes, filename)
    chords_call = run_chords.spawn(audio_bytes, filename, chord_dict)
    structure_call = run_structure.spawn(audio_bytes, filename)
    key_call = run_key.spawn(audio_bytes, filename)

    beats = beats_call.get()
    chords = chords_call.get()
    structure = structure_call.get()
    key = key_call.get()

    return {
        "path": filename,
        "bpm": beats["bpm"],
        "beats_per_bar": beats["beats_per_bar"],
        "beats": beats["beats"],
        "downbeats": beats["downbeats"],
        "segments": structure["segments"],
        "chords": chords["chords"],
        "key": key["key"],
        "_sources": {
            "beats": "madmom",
            "chords": f"chord-cnn-lstm ({chord_dict})",
            "structure": "songformer",
            "key": "essentia-key-extractor",
        },
    }


# ── Local CLI ──────────────────────────────────────────────────────────────────
@app.local_entrypoint()
def main(path: str, chord_dict: str = "full"):
    """modal run modal_chordmini.py --path track.mp3 [--chord-dict full]"""
    audio_path = pathlib.Path(path)
    print(f"Sending {audio_path.name} → Modal (beats + chords + structure)...")

    result = analyze_all.remote(
        audio_path.read_bytes(),
        audio_path.name,
        chord_dict,
    )

    out_dir = pathlib.Path(".appdata/maps/raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{audio_path.stem}.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nSaved: {out}")
    print(f"  bpm={result['bpm']}  beats_per_bar={result['beats_per_bar']}  key={result['key']}")
    print(f"  beats={len(result['beats'])}  downbeats={len(result['downbeats'])}")
    print(f"  segments={len(result['segments'])}  chords={len(result['chords'])}")
    print()
    print("Segments:")
    for s in result["segments"]:
        print(f"  {s['start']:7.2f}–{s['end']:7.2f}s  {s['label']}")
