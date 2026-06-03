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
from fastapi import Request
import sys, json, pathlib, base64

app = modal.App("recut-analyze")


def preload_model():
    from allin1.models import load_pretrained_model
    load_pretrained_model("harmonix-all", device="cpu")


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1", "libfftw3-dev", "build-essential", "git")
    .pip_install("torch==2.2.2", extra_index_url="https://download.pytorch.org/whl/cu121")
    .pip_install("torchaudio==2.2.2", extra_index_url="https://download.pytorch.org/whl/cu121")
    .pip_install("allin1==1.1.0", "numpy==1.26.4", "librosa==0.10.2", "soundfile", "fastapi[standard]")
    .run_commands("pip install natten==0.17.4+torch220cu121 --find-links https://shi-labs.com/natten/wheels/cu121/ --trusted-host shi-labs.com --no-deps")
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

        import allin1, base64
        demix_dir = tmp / "demix"
        r = allin1.analyze(
            str(audio_path),
            model="harmonix-all",
            device="cuda",
            multiprocess=False,
            demix_dir=str(demix_dir),
            spec_dir=str(tmp / "spec"),
            keep_byproducts=True,
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
            "stems": {},
        }

        if demix_dir.exists():
            stems = demix_dir.rglob("*.wav")
            for stem in stems:
                result["stems"][stem.name] = base64.b64encode(stem.read_bytes()).decode()
                
        print(f"allin1: bpm={result['bpm']} beats={len(result['beats'])} "
              f"downbeats={len(result['downbeats'])} segments={len(result['segments'])}"
              f" stems={len(result['stems'])}")
        return result


@app.function(image=image)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True)
async def analyze_web(request: Request):
    """POST multipart/form-data  file=@track.mp3  → allin1 JSON"""
    from fastapi.responses import JSONResponse
    form = await request.form()
    upload = form["file"]
    audio_bytes = await upload.read()
    filename = upload.filename or "track.mp3"
    result = await run_allin1.remote.aio(audio_bytes, filename)
    return JSONResponse(result)


@app.local_entrypoint()
def main(path: str):
    """modal run modal_pipeline.py --path path/to/track.mp3"""
    audio_path = pathlib.Path(path)
    stem = audio_path.stem
    out_dir = audio_path.parent

    print(f"Sending {path} to Modal GPU...")
    result = run_allin1.remote(open(path, "rb").read(), audio_path.name)

    out = out_dir / f"{stem}-allin1.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Saved: {out}")

    for filename, b64_string in result["stems"].items():
        stem_path = out_dir / filename
        stem_path.write_bytes(base64.b64decode(b64_string))
        print(f"Saved stem: {stem_path}")

    print(f"  bpm={result['bpm']}  beats={len(result['beats'])}  "
          f"downbeats={len(result['downbeats'])}  segments={len(result['segments'])}")
    print(f"\nNext steps:")
    print(f"  # get chords (h1zero docker or HF space):")
    print(f"  curl -X POST http://localhost:8000/analyze -F 'file=@{path}' -o {stem}-h1zero.json")
    print(f"  # merge everything:")
    print(f"  python modern-classic/merge_analysis.py '{path}' {stem}-allin1.json {stem}-h1zero.json")
