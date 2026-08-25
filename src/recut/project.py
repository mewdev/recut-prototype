import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from recut.compositor.effects import effect_from_json
from recut.compositor.nodes import Clip, Node, XFade
from recut.map.helpers import hash_file
from recut.map.parser import parse_recut_map
from recut.map.schema import MusicMap
from recut.paths import AUDIO_DIR, COMPOSITIONS_DIR, MAP_DIR, RAW_DIR

SourceStatus = Literal["ready", "needs_map", "needs_analysis", "hash_mismatch"]


@dataclass
class Source:
    name: str
    audio_path: Path
    music_map: Optional[MusicMap]
    status: SourceStatus


@dataclass
class Composition:
    name: str
    sources: list[str]
    nodes: list[Node]
    created: datetime


AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".m4a"}
COMPOSITION_EXTENSIONS = {".json"}


def load_project_sources() -> dict[str, Source]:
    sources = {}

    for audio_file in AUDIO_DIR.iterdir():
        if not (audio_file.is_file() and audio_file.suffix.lower() in AUDIO_EXTENSIONS):
            continue

        stem = audio_file.stem
        map_path = MAP_DIR / f"{stem}.json"

        if not map_path.exists():
            raw_path = RAW_DIR / f"{stem}.json"
            if not raw_path.exists():
                source = Source(
                    name=stem, audio_path=audio_file, music_map=None, status="needs_analysis"
                )
            else:
                source = Source(
                    name=stem, audio_path=audio_file, music_map=None, status="needs_map"
                )
        else:
            music_map = parse_recut_map(map_path)
            source = Source(name=stem, audio_path=audio_file, music_map=music_map, status="ready")
            if not verify_source_hash(source):
                source.status = "hash_mismatch"

        sources[stem] = source

    return sources


def verify_source_hash(source: Source) -> bool:

    if source.music_map is None:
        return False
    return hash_file(source.audio_path) == source.music_map.meta.audio_hash


def _nodes_to_json(nodes: list[Node]) -> list[dict]:
    """Serialize Clip/XFade node list to JSON-safe dicts."""
    result = []
    for node in nodes:
        if isinstance(node, Clip):
            result.append(
                {
                    "type": "clip",
                    "segment_name": node.segment_name,
                    "index": node.index,
                    "source": node.source,
                    "bars": node.bars,
                    "beats": node.beats,
                    "offset_bars": node.offset_bars,
                    "offset_beats": node.offset_beats,
                    "snap_to_downbeat": node.snap_to_downbeat,
                    "loop": node.loop,
                    "fx": [effect.to_json() for effect in node.fx],
                }
            )

        if isinstance(node, XFade):
            result.append(
                {"type": "xfade", "ms": node.ms, "curve": node.curve, "beats": node.beats}
            )

    return result


def _nodes_from_json(node_json: list[dict]) -> list[Node]:
    result = []
    # TODO: consider TypedDict for ClipDict/XFadeDict, etc. for type safety
    for node in node_json:
        fields = {k: v for k, v in node.items() if k != "type"}

        if node["type"] == "clip":
            fields["fx"] = [effect_from_json(effect_json) for effect_json in fields["fx"]]
            result.append(Clip(**fields))
        if node["type"] == "xfade":
            result.append(XFade(**fields))

    return result


def create_composition(name: str, sources: list[str] | None = None) -> Composition:
    return Composition(name=name, sources=sources or [], nodes=[], created=datetime.now())


def load_compositions() -> dict[str, Composition]:
    compositions = {}

    if not COMPOSITIONS_DIR.exists():
        return {}

    for composition_file in COMPOSITIONS_DIR.iterdir():
        if not (
            composition_file.is_file() and composition_file.suffix.lower() in COMPOSITION_EXTENSIONS
        ):
            continue

        composition_dict = json.loads(composition_file.read_text())
        nodes = _nodes_from_json(composition_dict["nodes"])

        composition = Composition(
            name=composition_dict["name"],
            sources=composition_dict["sources"],
            nodes=nodes,
            created=datetime.fromisoformat(composition_dict["created"]),
        )

        compositions[composition_file.stem] = composition

    return compositions


def save_composition(composition: Composition) -> None:

    COMPOSITIONS_DIR.mkdir(parents=True, exist_ok=True)

    composition_dict = {
        "name": composition.name,
        "sources": composition.sources,
        "nodes": _nodes_to_json(composition.nodes),
        "created": composition.created.isoformat(),
    }

    composition_json = json.dumps(composition_dict)

    path = COMPOSITIONS_DIR / f"{composition.name}.json"

    path.write_text(composition_json)
