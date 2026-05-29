import os
import sys
import json
import time
import tempfile
import traceback
import gc

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="H1-ZERO Chord Detection API")

# Allow CORS from any origin (SongPilot production site)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "service": "H1-ZERO Chord Detection", "version": "1.0.0"}

@app.get("/health")
def health():
    """Health check — verify models are loadable"""
    status = {
        "status": "healthy",
        "models": {}
    }

    try:
        import torch
        status["models"]["torch"] = torch.__version__
    except:
        status["models"]["torch"] = "not available"

    try:
        import librosa
        status["models"]["librosa"] = librosa.__version__
    except:
        status["models"]["librosa"] = "not available"

    status["models"]["hpss_bass"] = "available (librosa built-in)"

    try:
        from transformers import ClapModel
        status["models"]["clap"] = "available"
    except:
        status["models"]["clap"] = "not available"

    return status

@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    skip_demucs: bool = Form(False),
    skip_midi: bool = Form(False),
):
    """Run the full H1-ZERO pipeline on an uploaded audio file"""
    start_time = time.time()

    # Save uploaded file to temp
    suffix = os.path.splitext(file.filename or "audio.mp3")[1] or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from h1_zero_pipeline import run_h1_zero_pipeline

        result = run_h1_zero_pipeline(
            tmp_path,
            skip_demucs=skip_demucs,
            skip_midi=skip_midi
        )

        # Build response matching what SongPilot expects
        chords = result.get("final_chords", result.get("chords", []))

        # Normalize chord format
        normalized_chords = []
        for c in chords:
            normalized_chords.append({
                "time": c.get("time", c.get("timestamp", 0)),
                "chord": c.get("chord", "N"),
                "confidence": c.get("confidence", 0.8),
                "roman": c.get("roman", ""),
                "function": c.get("function", ""),
            })

        # Get additional metadata from result
        beats = result.get("beats", [])
        downbeats = result.get("downbeats", [])
        roman_numerals = result.get("roman_numerals", [])
        unique_chords = list(set(c["chord"] for c in normalized_chords if c["chord"] != "N"))

        response = {
            "success": True,
            "chords": normalized_chords,
            "key": result.get("key", "C"),
            "scale": result.get("scale", "major"),
            "genre": result.get("genre", "unknown"),
            "tempo": result.get("tempo", 120),
            "time_signature": result.get("time_signature", "4/4"),
            "confidence": result.get("key_confidence", result.get("confidence", 0.8)),
            "pipeline": "h1zero_full",
            "processing_time": round(time.time() - start_time, 2),
            "steps_completed": result.get("steps_completed", []),
            "beats": beats,
            "downbeats": downbeats,
            "roman_numerals": roman_numerals,
            "unique_chords": unique_chords,
            "environment": result.get("environment", "unknown"),
            "environment_confidence": result.get("environment_confidence", 0.5),
            "genre_confidence": result.get("genre_confidence", 0.5),
        }

        # Include MIDI if available
        if result.get("midi_base64"):
            response["midi_base64"] = result["midi_base64"]

        return JSONResponse(content=response)

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "processing_time": round(time.time() - start_time, 2),
            }
        )
    finally:
        # Cleanup
        try:
            os.unlink(tmp_path)
        except:
            pass
        gc.collect()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
