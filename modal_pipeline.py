"""
Recut Analysis Pipeline — Modal deployment

allin1 needs GPU. Everything else runs locally.

Usage:
    pip install modal
    modal deploy modal_pipeline.py

    # Run a track — saves track-allin1.json locally
    modal run modal_pipeline.py path/to/track.mp3

    # Then locally:
    python modern-classic/merge_analysis.py track.mp3 track-allin1.json track-h1zero.json

API:
    POST https://<workspace>--recut-analyze-web.modal.run/analyze
    Content-Type: multipart/form-data  field: file=@track.mp3
    Returns: { bpm, beats, downbeats, beat_positions, segments }
"""

import modal

app = modal.App("recut-analyze")


def preload_model():
    from allin1.models import load_pretrained_model
    load_pretrained_model("harmonix-all", device="cpu")


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1", "libfftw3-dev", "build-essential", "git")
    .pip_install("torch==2.2.2", extra_index_url="https://download.pytorch.org/whl/cu121")
    .pip_install("natten==0.14.6", extra_index_url="https://download.pytorch.org/whl/cu121")
    .pip_install("torchaudio==2.2.2", extra_index_url="https://download.pytorch.org/whl/cu121")
    .pip_install("allin1==1.1.0", "numpy==1.26.4", "librosa==0.10.2", "soundfile", "fastapi[standard]")
    .run_commands("pip install git+https://github.com/CPJKU/madmom")
    .run_function(preload_model)
)


@app.function(image=image, gpu="A10G", timeout=300, memory=8192)
def run_allin1(audio_bytes: bytes, filename: str = "track.mp3") -> dict:
    """GPU-only step: allin1 structure analysis."""
    import pathlib, tempfile, warnings
    warnings.filterwarnings("ignore")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        audio_path = tmp / filename
        audio_path.write_bytes(audio_bytes)

        import allin1
        r = allin1.analyze(
            str(audio_path),
            model="harmonix-all",
            device="cuda",
            multiprocess=False,
            demix_dir=str(tmp / "demix"),
            spec_dir=str(tmp / "spec"),
            keep_byproducts=False,
        )

        result = {
            "bpm":            r.bpm,
            "beats":          [round(float(b), 3) for b in r.beats],
            "downbeats":      [round(float(b), 3) for b in r.downbeats],
            "beat_positions": [int(p) for p in getattr(r, "beat_positions", [])],
            "segments": [
                {"label": s.label, "start": round(float(s.start), 3), "end": round(float(s.end), 3)}
                for s in r.segments
            ],
        }
        print(f"allin1: bpm={result['bpm']} beats={len(result['beats'])} "
              f"downbeats={len(result['downbeats'])} segments={len(result['segments'])}")
        return result


@app.function(image=image)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
async def analyze_web(request):
    """POST multipart/form-data  file=@track.mp3  → allin1 JSON"""
    from fastapi.responses import JSONResponse
    form = await request.form()
    upload = form["file"]
    audio_bytes = await upload.read()
    filename = upload.filename or "track.mp3"
    result = run_allin1.remote(audio_bytes, filename)
    return JSONResponse(result)


@app.local_entrypoint()
def main():
    """modal run modal_pipeline.py path/to/track.mp3"""
    import sys, json, pathlib
    if len(sys.argv) < 2:
        print("Usage: modal run modal_pipeline.py <path/to/track.mp3>")
        sys.exit(1)
    path = sys.argv[1]
    stem = pathlib.Path(path).stem

    print(f"Sending {path} to Modal GPU...")
    result = run_allin1.remote(open(path, "rb").read(), pathlib.Path(path).name)

    out = f"{stem}-allin1.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Saved: {out}")
    print(f"  bpm={result['bpm']}  beats={len(result['beats'])}  "
          f"downbeats={len(result['downbeats'])}  segments={len(result['segments'])}")
    print(f"\nNext steps:")
    print(f"  # get chords (h1zero docker or HF space):")
    print(f"  curl -X POST http://localhost:8000/analyze -F 'file=@{path}' -o {stem}-h1zero.json")
    print(f"  # merge everything:")
    print(f"  python modern-classic/merge_analysis.py '{path}' {stem}-allin1.json {stem}-h1zero.json")
