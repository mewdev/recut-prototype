"""recut CLI — music cutting system"""

import argparse
import json
import pathlib
import shutil
import time

from modal import Function

from recut.map.make_map import run as make_map
from recut.paths import AUDIO_DIR, MAP_DIR, RAW_DIR
from recut.project import load_compositions, load_project_sources

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

    print(f"Sending {filename} → Modal (beats + chords + structure)...")
    t0 = time.time()

    run_beats = Function.from_name(_APP, "run_beats")
    run_chords = Function.from_name(_APP, "run_chords")
    run_structure = Function.from_name(_APP, "run_structure")

    beats_call = run_beats.spawn(audio_bytes, filename)
    chords_call = run_chords.spawn(audio_bytes, filename)
    structure_call = run_structure.spawn(audio_bytes, filename)

    beats = beats_call.get()
    print(f"  ✓ beats      bpm={beats['bpm']}  ({time.time() - t0:.0f}s)")

    chords = chords_call.get()
    print(f"  ✓ chords     {len(chords['chords'])} chords  ({time.time() - t0:.0f}s)")

    structure = structure_call.get()
    print(f"  ✓ structure  {len(structure['segments'])} segments  ({time.time() - t0:.0f}s)")

    result = {
        "path": filename,
        "bpm": beats["bpm"],
        "time_signature": beats["time_signature"],
        "beats": beats["beats"],
        "downbeats": beats["downbeats"],
        "segments": structure["segments"],
        "chords": chords["chords"],
        "_sources": {
            "beats": "madmom",
            "chords": "chord-cnn-lstm (full)",
            "structure": "songformer",
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
