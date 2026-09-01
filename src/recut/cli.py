"""recut CLI — music cutting system"""

import argparse
import json
import pathlib
import shutil
import time

import soundfile as sf
from modal import Function

from recut.audio import Audio
from recut.compositor import compose
from recut.map.make_map import run as make_map
from recut.paths import AUDIO_DIR, MAP_DIR, RAW_DIR, RENDERS_DIR
from recut.project import Composition, Source, load_compositions, load_project_sources
from recut.validator import validate

_APP = "recut-analysis"

WELCOME = """
recut — declarative audio editing
───────────────────────────────────
Compose music cuts programmatically. Describe your edit in code,
recut renders it.

Commands:
  analyze   Analyze an audio file via Modal pipeline → raw JSON
  map       Build enriched maps for all sources that need it
  status    Show registry state for all sources in .appdata
  compositions  List saved compositions in .appdata/compositions
  validate  Validate a saved composition against its music map
  render    Validate and render a saved composition to audio

Run `recut <command> --help` for command-specific usage.
"""


def cmd_analyze(args) -> None:
    audio_path = pathlib.Path(args.audio)
    if not audio_path.exists():
        print(f"Error: file not found: {audio_path}")
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{audio_path.stem}.json"

    audio_bytes = audio_path.read_bytes()
    filename = audio_path.name

    print(f"Sending {filename} → Modal (beats + chords + structure + key)...")
    t0 = time.time()

    run_beats = Function.from_name(_APP, "run_beats")
    run_chords = Function.from_name(_APP, "run_chords")
    run_structure = Function.from_name(_APP, "run_structure")
    run_key = Function.from_name(_APP, "run_key")

    beats_call = run_beats.spawn(audio_bytes, filename)
    chords_call = run_chords.spawn(audio_bytes, filename)
    structure_call = run_structure.spawn(audio_bytes, filename)
    key_call = run_key.spawn(audio_bytes, filename)

    beats = beats_call.get()
    print(f"  ✓ beats      bpm={beats['bpm']}  ({time.time() - t0:.0f}s)")

    chords = chords_call.get()
    print(f"  ✓ chords     {len(chords['chords'])} chords  ({time.time() - t0:.0f}s)")

    structure = structure_call.get()
    print(f"  ✓ structure  {len(structure['segments'])} segments  ({time.time() - t0:.0f}s)")

    key = key_call.get()
    print(f"  ✓ key        {key['key']}  ({time.time() - t0:.0f}s)")

    result = {
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
            "chords": "chord-cnn-lstm (full)",
            "structure": "songformer",
            "key": "essentia-key-extractor",
        },
    }

    out_path.write_text(json.dumps(result, indent=2))
    print(f"Saved: {out_path.resolve()}")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audio_path, AUDIO_DIR)
    print(f"Copied audio → {(AUDIO_DIR / audio_path.name).resolve()}")


def cmd_map(args) -> None:
    """Build enriched maps for all sources with status=needs_map."""
    sources = load_project_sources()
    pending = {k: v for k, v in sources.items() if v.status == "needs_map"}

    if not pending:
        print("Nothing to map — all sources are up to date.")
        return

    MAP_DIR.mkdir(parents=True, exist_ok=True)

    for stem, source in pending.items():
        raw_path = RAW_DIR / f"{stem}.json"
        audio_path = source.audio_path
        map_path = MAP_DIR / f"{stem}.json"

        result = make_map(raw_path, audio_path)
        map_path.write_text(json.dumps(result.model_dump(), indent=2))
        print(f"  ✓ {stem}  duration={result.duration:.1f}s  segments={len(result.segments)}")


def cmd_status(args) -> None:
    """Show registry state for all sources in .appdata."""
    sources = load_project_sources()
    if not sources:
        print("No sources found in .appdata/audio/")
        return
    for source in sorted(sources.values(), key=lambda s: s.status):
        print(f"{source.name}: {source.status}")


def _resolve_composition(name: str) -> Composition:
    compositions = load_compositions()
    if name not in compositions:
        print(f"Error: composition not found: {name}")
        raise SystemExit(1)
    return compositions[name]


def _resolve_source(composition: Composition) -> Source:
    if not composition.sources:
        print(f"Error: composition {composition.name!r} has no sources")
        raise SystemExit(1)

    sources = load_project_sources()
    name = composition.sources[0]
    source = sources.get(name)
    if source is None or source.music_map is None:
        print(f"Error: source {name!r} not ready — run `recut map` first")
        raise SystemExit(1)
    return source


def cmd_validate(args) -> None:
    """Validate a saved composition against its source's music map."""
    composition = _resolve_composition(args.name)
    source = _resolve_source(composition)

    issues = validate(source.music_map, *composition.nodes)
    for issue in issues:
        print(f"{issue.severity}: {issue.message}")

    if not issues:
        print("OK — no issues")
    if any(issue.severity == "error" for issue in issues):
        raise SystemExit(1)


def cmd_render(args) -> None:
    """Validate a saved composition, then render it to audio.

    `_resolve_composition`/`_resolve_source` above already give you the
    Composition and its Source (source.audio_path, source.music_map).
    """
    composition = _resolve_composition(args.name)
    source = _resolve_source(composition)

    issues = validate(source.music_map, *composition.nodes)
    for issue in issues:
        print(f"{issue.severity}: {issue.message}")

    has_errors = any(issue.severity == "error" for issue in issues)
    if has_errors and not args.force:
        print("Aborting render — fix the errors above, or pass --force.")
        raise SystemExit(1)

    audio = Audio.load(str(source.audio_path))
    result = compose(source.music_map, audio, *composition.nodes)

    RENDERS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = pathlib.Path(args.out) if args.out else RENDERS_DIR / f"{composition.name}.mp3"
    sf.write(out_path, result.samples.T, result.sr)
    print(f"Rendered: {out_path.resolve()}")


def cmd_compositions(args) -> None:
    """List saved compositions in .appdata/compositions"""
    compositions = load_compositions()
    if not compositions:
        print("No compositions found in .appdata/compositions/")
        return
    for composition in sorted(compositions.values(), key=lambda s: s.created):
        print(f"{composition.name} (created: {composition.created})")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="recut",
        description="Declarative audio editing — compose music cuts programmatically",
        epilog="Docs: see src/analysis/README.md for pipeline setup",
    )

    sub = parser.add_subparsers(dest="command")

    analyze = sub.add_parser("analyze", help="Analyze audio via Modal pipeline → raw JSON")
    analyze.add_argument("audio", help="path to audio file (mp3, wav, ...)")
    analyze.set_defaults(func=cmd_analyze)

    map_cmd = sub.add_parser("map", help="Build enriched maps for all needs_map sources")
    map_cmd.set_defaults(func=cmd_map)

    status_cmd = sub.add_parser("status", help="Show registry state for all sources")
    status_cmd.set_defaults(func=cmd_status)

    composition_cmd = sub.add_parser("compositions", help="Show compositions")
    composition_cmd.set_defaults(func=cmd_compositions)

    validate_cmd = sub.add_parser("validate", help="Validate a saved composition")
    validate_cmd.add_argument("name", help="composition name")
    validate_cmd.set_defaults(func=cmd_validate)

    render_cmd = sub.add_parser("render", help="Validate and render a saved composition")
    render_cmd.add_argument("name", help="composition name")
    render_cmd.add_argument("--out", help="output audio path (default: .appdata/renders/<name>.mp3)")
    render_cmd.add_argument(
        "--force", action="store_true", help="render despite error-severity validation issues"
    )
    render_cmd.set_defaults(func=cmd_render)

    args = parser.parse_args()

    if not args.command:
        print(WELCOME)
        return

    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
