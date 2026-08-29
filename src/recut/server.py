"""
recut backend API — general HTTP entry point for the ui/ frontend, not tied
to any one feature. Registry/source endpoints today; more will be added
here as the app grows (composition, LLM orchestration, etc).

Run from repo root: uvicorn recut.server:app --port 5050 --reload
The ui/ Vite dev server proxies /sources, /map, /audio here.

OpenAPI schema (auto-generated from these Pydantic models) is served at
/openapi.json — the frontend generates its typed client from it. Interactive
docs at /docs.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from recut.map.schema import MusicMap
from recut.project import Source, load_project_sources

app = FastAPI(title="recut API", version="1.0.0")


class SourceSummary(BaseModel):
    name: str
    status: str


def _ready_source(name: str) -> Source:
    source = load_project_sources().get(name)
    if source is None or source.status != "ready":
        raise HTTPException(status_code=404)
    return source


@app.get("/sources", response_model=list[SourceSummary])
def load_sources():
    sources = load_project_sources()
    return [{"name": k, "status": v.status} for k, v in sources.items()]


@app.get("/map/{name}", response_model=MusicMap)
def load_map(name: str):
    source = _ready_source(name)
    assert source.music_map is not None
    return source.music_map


@app.get("/audio/{name}")
def load_audio(name: str):
    source = _ready_source(name)
    return FileResponse(source.audio_path.resolve())
