"""recut CLI — music cutting system"""

import argparse
import json
import pathlib
import time

from modal import Function

from map.make_map import run as make_map

_APP = "recut-analysis"

WELCOME = """
recut — declarative audio editing
───────────────────────────────────
Compose music cuts programmatically. Describe your edit in code,
recut renders it.

Commands:
  analyze   Analyze an audio file via Modal pipeline → raw JSON
  map       Build an enriched music map from raw analysis output

Run `recut <command> --help` for command-specific usage.
"""

RAW_DIR = pathlib.Path("temp/analysis/raw")
MAP_DIR = pathlib.Path("temp/analysis/maps")


def cmd_analyze(args) -> None:
    audio_path = pathlib.Path(args.audio)
    if not audio_path.exists():
        print(f"Error: file not found: {audio_path}")
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{audio_path.stem}-raw.json"

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


def cmd_map(args) -> None:
    audio_path = pathlib.Path(args.audio)
    raw_path = pathlib.Path(args.raw)

    if not audio_path.exists():
        print(f"Error: audio file not found: {audio_path}")
        return
    if not raw_path.exists():
        print(f"Error: raw JSON not found: {raw_path}")
        return

    MAP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = MAP_DIR / f"{audio_path.stem}-map.json"

    print(f"Building music map for {audio_path.name}...")
    result = make_map(str(raw_path), str(audio_path))

    out_path.write_text(json.dumps(result, indent=2))
    print(f"Saved: {out_path.resolve()}")
    print(f"  duration={result['duration']:.1f}s  segments={len(result['segments'])}  bars={len(result['bars'])}")


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

    map_cmd = sub.add_parser("map", help="Build music map from raw analysis JSON")
    map_cmd.add_argument("audio", help="path to audio file (mp3, wav, ...)")
    map_cmd.add_argument("raw", help="path to raw analysis JSON (-raw.json)")
    map_cmd.set_defaults(func=cmd_map)

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
