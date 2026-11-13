# One image for every host (Intel Mac via Docker Desktop, Arch, the VPS later).
# linux/amd64: Essentia ships wheels for it (Q1 adds the `qc` extra; until then, `.[dev]`).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Source is copied in full: the editable install points at /app/src, and tests/ and
# examples/ ship with the image so `docker compose run --rm recut python -m pytest tests/ -q`
# and `recut ticket demo` work. No secrets go in: .env and ~/.modal.toml are mounted at run time.
COPY . /app
RUN pip install -e ".[dev]"

EXPOSE 8000

CMD ["recut", "serve", "--host", "0.0.0.0", "--port", "8000"]
