"""
Full ChordMiniApp analysis pipeline on Modal

Replicates what chordmini.me does when you upload a track:
  1. Beats    — madmom (RNN + DBN beat tracking)
  2. Chords   — Chord-CNN-LSTM (5-model ensemble → .lab → JSON)
  3. Structure — SongFormer (MuQ + MusicFM embeddings → section labels)

All three run in parallel Modal containers, then merge into one JSON.

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
      "time_signature": "4/4",
      "beats": [0.51, 1.02, ...],
      "downbeats": [0.51, 2.55, ...],
      "segments": [{"start": "0.0", "end": "12.5", "label": "intro"}, ...],
      "chords": [{"start": 0.0, "end": 2.3, "chord": "F#:min", "confidence": 1.0}, ...],
      "_sources": { "beats": "madmom", "chords": "chord-cnn-lstm (full)", "structure": "songformer" }
    }
"""

import json
import pathlib

import modal

app = modal.App("recut-chordmini")

# TODO: we should run form one source, no separated local / remote models
# ── Local model paths ──────────────────────────────────────────────────────────
_PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
CHORD_MODEL_LOCAL = _PROJECT_ROOT / "archive/ChordMiniApp/python_backend/models/Chord-CNN-LSTM"
SONGFORMER_LOCAL  = _PROJECT_ROOT / "archive/ChordMiniApp/SongFormer"

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
    _base
    .apt_install("git")
    .pip_install("setuptools<81")    # madmom needs pkg_resources from setuptools
    .run_commands("pip install git+https://github.com/CPJKU/madmom")
)

chords_image = (
    _base
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
    .add_local_dir(str(CHORD_MODEL_LOCAL), remote_path="/chord_model")
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
    _base_cuda
    .pip_install(
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
    .add_local_dir(str(SONGFORMER_LOCAL), remote_path="/songformer", copy=True)
    # Both MuQ and MusicFM weights are Git LFS pointers locally — download the real
    # weights from HuggingFace at image build time (result is cached by Modal).
    .run_commands(
        "python -c \""
        "from huggingface_hub import hf_hub_download; "
        "import shutil; "
        "src = hf_hub_download('OpenMuQ/MuQ-large-msd-iter', 'model.safetensors'); "
        "shutil.copy(src, '/songformer/src/SongFormer/ckpts/MuQ/model.safetensors'); "
        "print('MuQ weights downloaded OK')"
        "\""
    )
    .run_commands(
        "python -c \""
        "from huggingface_hub import hf_hub_download; "
        "import shutil; "
        "src = hf_hub_download('minzwon/MusicFM', 'pretrained_msd.pt'); "
        "shutil.copy(src, '/songformer/src/SongFormer/ckpts/MusicFM/pretrained_msd.pt'); "
        "print('MusicFM weights downloaded OK')"
        "\""
    )
    .run_commands(
        "apt-get install -y -q curl && "
        "curl -L -o /songformer/src/SongFormer/ckpts/SongFormer.safetensors "
        "'https://media.githubusercontent.com/media/ptnghia-j/ChordMiniApp/main/SongFormer/src/SongFormer/ckpts/SongFormer.safetensors' && "
        "echo 'SongFormer checkpoint downloaded OK'"
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
        from madmom.features.beats import DBNBeatTrackingProcessor, RNNBeatProcessor

        beat_activation = RNNBeatProcessor()(str(audio_path))
        beat_times = DBNBeatTrackingProcessor(fps=100)(beat_activation)

        bpm = 120.0
        if len(beat_times) > 1:
            median_interval = np.median(np.diff(beat_times))
            bpm = 60.0 / median_interval if median_interval > 0 else 120.0

        downbeats = beat_times[::4]   # assume 4/4; frontend can override
        elapsed = round(time.time() - t0, 2)
        print(f"madmom: {len(beat_times)} beats  bpm={bpm:.1f}  {elapsed}s")

        return {
            "beats":          [round(float(b), 3) for b in beat_times],
            "downbeats":      [round(float(b), 3) for b in downbeats],
            "bpm":            round(bpm, 2),
            "time_signature": "4/4",
            "model":          "madmom",
        }


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
                    chords.append({
                        "start": round(float(parts[0]), 3),
                        "end":   round(float(parts[1]), 3),
                        "chord": parts[2],
                    })

        elapsed = round(time.time() - t0, 2)
        print(f"chord-cnn-lstm: {len(chords)} chords  dict={chord_dict}  {elapsed}s")

        return {
            "chords":       chords,
            "total_chords": len(chords),
            "duration":     chords[-1]["end"] if chords else 0.0,
            "chord_dict":   chord_dict,
            "model":        "chord-cnn-lstm",
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
        module = importlib.util.module_from_spec(spec)
        sys.modules["songformer_app"] = module
        # app.py does os.chdir(SONGFORMER_SRC_DIR) at module level — that's fine,
        # all model file paths inside it are relative to that dir.
        spec.loader.exec_module(module)

        t0 = time.time()
        module.initialize_models()

        msa_output = module.process_audio(str(audio_path))
        cleaned    = module.rule_post_processing(msa_output)
        segments   = module.format_as_segments(cleaned)

        elapsed = round(time.time() - t0, 2)
        print(f"songformer: {len(segments)} segments  {elapsed}s")

        # convert start/end strings → floats for consistency
        for seg in segments:
            seg["start"] = float(seg["start"])
            seg["end"]   = float(seg["end"])

        return {
            "segments": segments,
            "model":    "songformer",
        }


# ── Orchestrator: run all three in parallel ────────────────────────────────────
@app.function(image=_base, timeout=1200)
def analyze_all(audio_bytes: bytes, filename: str = "track.mp3", chord_dict: str = "full") -> dict:
    """Spawn beats + chords + structure in parallel, merge into one JSON."""
    # spawn = fire-and-forget; returns a handle we .get() later
    beats_call     = run_beats.spawn(audio_bytes, filename)
    chords_call    = run_chords.spawn(audio_bytes, filename, chord_dict)
    structure_call = run_structure.spawn(audio_bytes, filename)

    beats     = beats_call.get()
    chords    = chords_call.get()
    structure = structure_call.get()

    return {
        "path":           filename,
        "bpm":            beats["bpm"],
        "time_signature": beats["time_signature"],
        "beats":          beats["beats"],
        "downbeats":      beats["downbeats"],
        "segments":       structure["segments"],
        "chords":         chords["chords"],
        "_sources": {
            "beats":     "madmom",
            "chords":    f"chord-cnn-lstm ({chord_dict})",
            "structure": "songformer",
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

    out = audio_path.parent / f"{audio_path.stem}-chordmini.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nSaved: {out}")
    print(f"  bpm={result['bpm']}  time_sig={result['time_signature']}")
    print(f"  beats={len(result['beats'])}  downbeats={len(result['downbeats'])}")
    print(f"  segments={len(result['segments'])}  chords={len(result['chords'])}")
    print()
    print("Segments:")
    for s in result["segments"]:
        print(f"  {s['start']:7.2f}–{s['end']:7.2f}s  {s['label']}")
