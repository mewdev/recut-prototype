"""recut CLI — music cutting system"""

import argparse

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


def cmd_analyze(args) -> None:
    print(f"[analyze] would run Modal pipeline on: {args.audio}")
    print("[analyze] → temp/analysis/raw/<stem>-raw.json")


def cmd_map(args) -> None:
    print(f"[map] would run make_map on: {args.raw}")
    print(f"[map] audio: {args.audio}")
    print("[map] → temp/analysis/maps/<stem>-map.json")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="recut",
        description="Declarative audio editing — compose music cuts programmatically",
        epilog="Docs: see src/analysis/README.md for pipeline setup",
    )

    sub = parser.add_subparsers(dest="command")

    analyze = sub.add_parser("analyze", help="Analyze audio via Modal pipeline → raw JSON")
    make_map = sub.add_parser("map", help="Build music map from raw analysis JSON")

    analyze.add_argument("audio", help="path to audio file (mp3, wav, ...)")
    make_map.add_argument("audio", help="path to audio file (mp3, wav, ...)")
    make_map.add_argument("raw", help="path to raw analysis JSON (-raw.json)")

    analyze.set_defaults(func=cmd_analyze)
    make_map.set_defaults(func=cmd_map)

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
