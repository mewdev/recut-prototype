FROM python:3.11-slim

# System deps for audio processing + build tools for madmom C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libfftw3-dev \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Core audio processing (no GPU, no PyTorch needed — HPSS is pure librosa)
RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    scipy \
    librosa==0.10.2 \
    soundfile \
    pydub

# CLAP for genre classification (needs torch + transformers)
RUN pip install --no-cache-dir \
    torch==2.1.2 --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir transformers==4.40.0

# BeatNet for beat detection (madmom needs Cython + gcc to build)
RUN pip install --no-cache-dir Cython
RUN pip install --no-cache-dir \
    madmom==0.16.1 \
    onnxruntime==1.17.1

# HMM smoothing
RUN pip install --no-cache-dir hmmlearn==0.3.2

# Music theory
RUN pip install --no-cache-dir music21==9.1.0

# Essentia for tonal features
RUN pip install --no-cache-dir essentia==2.1b6.dev1110 || \
    pip install --no-cache-dir essentia-tensorflow==2.1b6.dev1110 || \
    echo "Essentia install optional - will use librosa fallback"

# Basic Pitch for AMT
RUN pip install --no-cache-dir basic-pitch==0.3.3 || \
    echo "Basic Pitch install optional"

# MIDI
RUN pip install --no-cache-dir mido==1.3.2

# FastAPI server
RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    uvicorn==0.30.1 \
    python-multipart

# Cache bust to force re-copy of pipeline files
ARG PIPELINE_VERSION=v7_hpss_fast_20260316
COPY h1_zero_pipeline.py .
COPY api.py .

# Pre-download CLAP model (cached in image)
RUN python -c "import warnings; warnings.filterwarnings('ignore'); \
try: \
    from transformers import ClapModel, ClapProcessor; \
    m = ClapModel.from_pretrained('laion/larger_clap_music'); \
    p = ClapProcessor.from_pretrained('laion/larger_clap_music'); \
    del m, p; \
    print('CLAP model cached'); \
except Exception as e: \
    print(f'CLAP cache failed: {e}')" || echo "CLAP pre-cache skipped"

# Expose port 7860 (HuggingFace Spaces default)
EXPOSE 7860

# Start the API server
CMD ["python", "api.py"]
