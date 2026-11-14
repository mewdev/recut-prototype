"""recut CLI — music cutting system"""

import argparse
import json
import pathlib
import shutil
from datetime import datetime

import soundfile as sf

from recut.analysis_client import analyze_raw
from recut.audio import Audio
from recut.compositor import compose
from recut.map.make_map import run as make_map
from recut.paths import AUDIO_DIR, MAP_DIR, RAW_DIR, RENDERS_DIR, TICKETS_DIR
from recut.project import Composition, Source, load_compositions, load_project_sources
from recut.report import parse_date
from recut.validator import validate

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
  ticket    Client edit tickets: new, list, work, iterate, render, demo, import-legacy
  report    Numbers for the weekly improvement pass (reads tickets only)
  serve     Review server with live browser preview (http://localhost:8000)

Run `recut <command> --help` for command-specific usage.
"""


def cmd_analyze(args) -> None:
    audio_path = pathlib.Path(args.audio)
    if not audio_path.exists():
        print(f"Error: file not found: {audio_path}")
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{audio_path.stem}.json"
    result = analyze_raw(audio_path)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"Saved: {out_path.resolve()}")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audio_path, AUDIO_DIR)
    print(f"Copied audio → {(AUDIO_DIR / audio_path.name).resolve()}")


def cmd_map(args) -> None:
    """Build enriched maps for all sources with status=needs_map (--force: rebuild existing)."""
    sources = load_project_sources()
    force = getattr(args, "force", False)
    stems = getattr(args, "stems", None) or []
    if getattr(args, "enrich", False):
        return _enrich_sources(sources, stems)
    unknown = [s for s in stems if s not in sources]
    if unknown:
        print(f"Error: unknown source(s): {', '.join(unknown)}")
        raise SystemExit(1)
    if force:
        # rebuild every source that has raw analysis (or just the named ones)
        pending = {
            k: v for k, v in sources.items()
            if (not stems or k in stems) and (RAW_DIR / f"{k}.json").exists()
        }
        for s in stems:
            if s not in pending:
                print(f"  skipped {s}: no raw analysis (run `recut analyze` first)")
    else:
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


def _enrich_sources(sources, stems) -> None:
    """`recut map --enrich`: add pace / loudness / key ranges to existing maps, no re-analysis."""
    from recut.map.enrich import enrich_map_file

    unknown = [s for s in stems if s not in sources]
    if unknown:
        print(f"Error: unknown source(s): {', '.join(unknown)}")
        raise SystemExit(1)
    done = False
    for stem, source in sources.items():
        if stems and stem not in stems:
            continue
        map_path = MAP_DIR / f"{stem}.json"
        if not map_path.exists():
            print(f"  skipped {stem}: no map yet (run `recut map`)")
            continue
        done = True
        changed = enrich_map_file(map_path, source.audio_path, force=bool(stems))
        print(f"  {'✓ enriched' if changed else '= already has pace/loudness/key ranges:'} {stem}")
    if not done:
        print("Nothing to enrich.")


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


def cmd_check_audio(args) -> None:
    from recut import intake

    bad = 0
    for f in args.files:
        res = intake.check_audio(f)
        print(intake.format_result(pathlib.Path(f).name, res))
        bad += not res.ok
    if bad:
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


def cmd_serve(args) -> None:
    import uvicorn

    from recut import sync

    repo = sync.repo_root(TICKETS_DIR)
    print(f"recut review server → http://{args.host}:{args.port}  (tickets: {TICKETS_DIR.resolve()})")
    print(f"data repo: {repo} (auto-sync {'on' if sync.enabled() else 'off'})" if repo
          else "data repo: none — tickets stay local (clone mewdev/recut-data next to this repo)")
    from recut import tickets

    reminder = tickets.awaiting_client_message()
    if reminder:
        print("\n" + reminder + "\n")
    uvicorn.run("recut.server.app:app", host=args.host, port=args.port, reload=args.reload,
                log_level="warning")


def _intent_snippet(tid: str) -> str:
    from recut import tickets

    return json.dumps({"target_duration_s": tickets.load_request(tid).target_duration_s,
                       "must_keep": [], "must_cut": [], "ending": None, "notes": None}, indent=2)


def _print_work_instructions(tid: str, n: int, k: int) -> None:
    from recut import tickets

    d = tickets.ticket_dir(tid)
    sd = tickets.session_dir(tid, n)
    review = None
    if n > 1:
        review = tickets.load_review(tid, n - 1)
    snippet = "\n".join("    " + line for line in _intent_snippet(tid).splitlines())
    print(f"""
Ticket {tid} · session {n} · iteration {k}

  request:   {d / "request.json"}
  sources:   {json.dumps(tickets.sources(tid))}
  last review: {sd.parent / str(n - 1) / "review.json" if review else "(none)"}
  edit plan: {tickets.iteration_dir(tid, n, k) / "plan.json"}

  export RECUT_SESSION={sd.resolve()}

STEP 1 — write {sd / "intent.json"} BEFORE cutting (how you read the request; fill in, keep
these keys, no others):
{snippet}
STEP 2 — edit plan.json (format: docs/PLAN.md §3.2) — the browser preview re-renders on save.
         In plan.notes write what you changed and why (every iteration).
Check without the browser:  recut ticket render {tid}   (it warns about a missing intent.json
                            and unchanged plan.notes)
Next attempt:               recut ticket iterate {tid}

Transcript: if the operator enabled the Stop hook (AGENTS.md, "Working a client ticket"),
your transcript is copied to {sd / "transcript.jsonl"} automatically.
""")


def cmd_sync(args) -> None:
    from recut import sync

    res = sync.sync(TICKETS_DIR, message=args.message)
    if not args.quiet or res["status"] not in ("pushed", "clean", "committed", "no-data-repo"):
        print(f"sync: {res['status']}" + (f" ({res['error']})" if res.get("error") else "")
              + ("" if res["status"] != "no-data-repo" else
                 f" — tickets are in {TICKETS_DIR}; clone mewdev/recut-data next to this repo to save them remotely"))


def cmd_ticket(args) -> None:
    try:
        _cmd_ticket(args)
    finally:
        # import-legacy syncs only the default store (a --root elsewhere is not the data repo)
        if args.action in ("new", "demo", "work", "iterate", "render", "client", "usage", "share", "enrich") or (
                args.action == "import-legacy" and args.root is None):
            from recut import sync

            res = sync.request_sync(f"ticket {args.action} {getattr(args, 'id', '') or ''}".strip(), TICKETS_DIR, wait=True)
            if res and res["status"] in ("push-failed", "error"):
                print(f"(data sync failed: {res.get('error', '')[:200]} — run `recut sync` to retry)")


def _cmd_ticket(args) -> None:
    from recut import tickets

    if args.action == "new":
        files = [(pathlib.Path(f).name, pathlib.Path(f)) for f in args.files]
        for _, f in files:
            if not f.exists():
                print(f"Error: file not found: {f}")
                raise SystemExit(1)
        from recut import intake

        checks = [(name, intake.check_audio(f)) for name, f in files]
        for name, res in checks:
            if res.problems:
                print(intake.format_result(name, res))
        if any(not r.ok for _, r in checks):
            if not args.override:
                print("\nNot created: fix the blocking problems above (the messages can be forwarded to the "
                      "client), or re-run with --override to use these files anyway.")
                raise SystemExit(1)
            print("\n--override: creating the ticket despite the blocking problems.")
        tid = tickets.create_ticket(args.text, files, args.duration)
        tickets.record_intake(tid, checks, override=bool(args.override and any(not r.ok for _, r in checks)))
        print(f"Created ticket {tid}")
    elif args.action == "list":
        waiting = {it["id"] for it in tickets.awaiting_client()}
        for r in tickets.list_tickets():
            flag = "  ⚠ awaiting client feedback" if r.id in waiting else ""
            print(f"{r.id}  {r.status:<14} {r.text[:70]}{flag}")
    elif args.action == "awaiting":
        msg = tickets.awaiting_client_message()
        if msg:
            print(msg)
        elif not args.quiet:
            print("No shipped cuts are waiting for client feedback.")
    elif args.action == "demo":
        tid = tickets.create_demo_ticket()
        print(f"Created demo ticket {tid} with 2 rendered iterations.\n"
              f"Run `recut serve` and open http://localhost:8000/t/{tid}")
    elif args.action == "work":
        tid = args.id
        mapped = tickets.ensure_maps(tid)
        if mapped:
            print(f"Analyzed + mapped sources: {', '.join(mapped)}")
        n = tickets.new_session(tid, agent=args.agent, model=args.model)
        tickets.mark_current_session(tid, n)
        k = tickets.new_iteration(tid, n, plan=None if tickets.latest_plan(tid) else _starter_plan(tid))
        _print_work_instructions(tid, n, k)
    elif args.action == "enrich":
        done = tickets.enrich_maps(args.id, force=args.force)
        print(f"Enriched maps (pace, loudness, key ranges): {', '.join(done)}" if done
              else "Maps already have pace / loudness / key ranges (use --force to recompute).")
    elif args.action == "iterate":
        tid = args.id
        sessions = tickets.session_numbers(tid)
        if not sessions:
            print(f"No session yet — run `recut ticket work {tid}` first")
            raise SystemExit(1)
        n = sessions[-1]
        k = tickets.new_iteration(tid, n)
        print(f"New iteration: {tickets.iteration_dir(tid, n, k) / 'plan.json'} (copied from the previous one)")
    elif args.action == "client":
        tid = args.id
        try:
            fb = tickets.add_client_feedback(
                tid, "approved" if args.approved else "changes", rating=args.rating,
                note=args.note, session=args.session, iteration=args.iteration)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}")
            raise SystemExit(1)
        if args.session is not None or args.iteration is not None:
            how = "given"
        elif (rv := tickets.load_iteration_review(tid, fb.session, fb.iteration)) and rv.verdict == "ship":
            how = "latest shipped"
        else:
            how = "no ship review yet: latest iteration"
        stars = f" ★{fb.rating}" if fb.rating else ""
        print(f"Recorded client {fb.decision}{stars} on s{fb.session}·it{fb.iteration} ({how}) · ticket {tid} "
              f"→ {'client_approved' if fb.decision == 'approved' else 'client_changes'}")
        if fb.note:
            print(f"  note: {fb.note}")
    elif args.action in ("usage", "show"):
        from recut import usage

        tid = args.id
        try:
            tickets.ticket_dir(tid)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            raise SystemExit(1)
        usage.refresh_stale(TICKETS_DIR, tid)
        if args.action == "show":
            print(f"{tid}  {tickets.load_request(tid).status}")
            for ev in tickets.ticket_timeline(tid):
                extra = " ".join(f"{k}={v}" for k, v in ev.items()
                                 if k not in ("ts", "op", "derived") and v is not None)
                print(f"  {ev['ts']}  {ev['op']:<16}{extra}{'  (derived)' if ev.get('derived') else ''}")
        for n in tickets.session_numbers(tid):
            u = usage.load_usage(tickets.session_dir(tid, n))
            if u is None:
                print(f"s{n}: no usage (no transcript)")
                continue
            cost = f"${u['cost_usd']:.2f}" if u.get("cost_usd") is not None else "cost n/a"
            print(f"s{n}: {u.get('model')}  in {u['input_tokens']:,} out {u['output_tokens']:,} "
                  f"cache r/w {u['cache_read_tokens']:,}/{u['cache_write_tokens']:,}  "
                  f"{u['duration_s'] / 60:.1f} min  {u['turns']} turns  {cost}")
    elif args.action == "import-legacy":
        from recut import legacy_import

        root = args.root or TICKETS_DIR
        try:
            tid = legacy_import.import_export(args.export_dir, root, force=args.force)
        except (FileExistsError, FileNotFoundError, ValueError) as e:
            print(f"Error: {e}")
            raise SystemExit(1)
        print(f"Imported {args.export_dir.name} as baseline ticket {tid} (agent legacy-pre-refactor) in {root}\n"
              f"Check: recut report --root {root}")
    elif args.action == "render":
        tid = args.id
        n = args.session or tickets.session_numbers(tid)[-1]
        k = args.iteration or tickets.iteration_numbers(tid, n)[-1]
        out = tickets.render_iteration(tid, n, k)
        if "error" in out:
            print(f"Render FAILED: {out['error']}")
            raise SystemExit(1)
        print(f"Rendered s{n}·it{k}: {out['duration_s']:.1f}s, {len(out['splices'])} splices")
        for i in out["issues"]:
            where = i.get("splice") or i.get("node") or ""
            print(f"  {i['severity']:<5} {i['rule']:<14} {where:<4} {i['message']}")
        for w in tickets.process_warnings(tid, n, k):
            print(f"  WARNING (process): {w}")


def cmd_report(args) -> None:
    from recut import report

    data = report.build(args.root, since=args.since)
    if args.html:
        from recut.report_html import render_html

        out = args.out or pathlib.Path("recut-report.html")
        out.write_text(render_html(data, generated=datetime.now().strftime("%Y-%m-%d %H:%M")))
        print(f"wrote {out}")
    elif args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(report.format_text(data))


def _rating(text: str) -> int:
    try:
        v = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected 1-5, got {text!r}") from None
    if not 1 <= v <= 5:
        raise argparse.ArgumentTypeError(f"expected 1-5, got {v}")
    return v


def _starter_plan(tid: str) -> dict:
    """Minimal valid plan for a fresh ticket: first source, first section. The agent replaces it."""
    from recut import tickets
    from recut.map.parser import parse_recut_map

    srcs = tickets.sources(tid)
    d = tickets.ticket_dir(tid)
    sid = next(iter(srcs))
    m = parse_recut_map(d / srcs[sid]["map"])
    first = next(s for s in m.segments if s.segment_name != "silence")
    return {
        "version": 2,
        "sources": {k: {"file": v["file"], "map": v["map"]} for k, v in srcs.items()},
        "tracks": [{"id": "main", "clips": [
            {"id": "n1", "type": "clip", "source": sid, "segment": first.segment_name, "index": 1}]}],
        "target_duration_s": tickets.load_request(tid).target_duration_s,
        "notes": "starter plan — replace with the real edit",
    }


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
    map_cmd.add_argument("--force", action="store_true",
                         help="rebuild existing enriched maps too (after a map fix)")
    map_cmd.add_argument("--enrich", action="store_true",
                         help="add pace / short-term loudness / key ranges to existing maps "
                              "(no re-analysis; named stems are recomputed)")
    map_cmd.add_argument("stems", nargs="*", help="with --force / --enrich: only these sources")
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

    ca = sub.add_parser("check-audio", help="Intake check: bitrate, real bandwidth, sample rate, length")
    ca.add_argument("files", nargs="+")
    ca.set_defaults(func=cmd_check_audio)

    ticket_cmd = sub.add_parser("ticket", help="Client edit tickets")
    tsub = ticket_cmd.add_subparsers(dest="action", required=True)
    t_new = tsub.add_parser("new", help="Create a ticket from audio files + request text")
    t_new.add_argument("files", nargs="+")
    t_new.add_argument("--text", required=True, help="the client's request, verbatim")
    t_new.add_argument("--duration", type=float, help="target duration in seconds")
    t_new.add_argument("--override", action="store_true",
                       help="create the ticket even if the intake check finds blocking problems")
    tsub.add_parser("list", help="List tickets")
    t_aw = tsub.add_parser("awaiting", help="Shipped cuts with no client feedback logged yet")
    t_aw.add_argument("--quiet", action="store_true", help="print nothing when none (for hooks)")
    tsub.add_parser("demo", help="Create a demo ticket from examples/summer-party")
    t_work = tsub.add_parser("work", help="Start an agent session (analyzes unmapped sources)")
    t_work.add_argument("id")
    t_work.add_argument("--agent", default="claude-code")
    t_work.add_argument("--model", help="model doing the cut, e.g. sonnet — logged for comparison")
    t_en = tsub.add_parser("enrich", help="Add pace / loudness / key ranges to the ticket's existing maps")
    t_en.add_argument("id")
    t_en.add_argument("--force", action="store_true", help="recompute even if present")
    t_it = tsub.add_parser("iterate", help="New iteration in the latest session (copies the plan)")
    t_it.add_argument("id")
    t_c = tsub.add_parser("client", help="Log the client's decision on a delivered cut")
    t_c.add_argument("id")
    t_cd = t_c.add_mutually_exclusive_group(required=True)
    t_cd.add_argument("--approved", action="store_true", help="the client approves the cut")
    t_cd.add_argument("--changes", action="store_true", help="the client asks for changes")
    t_c.add_argument("--rating", type=_rating, help="client satisfaction, 1-5")
    t_c.add_argument("--note", help="what the client said, verbatim when possible")
    t_c.add_argument("--session", type=int, help="session (default: the latest shipped iteration)")
    t_c.add_argument("--iteration", type=int, help="iteration (default: the latest shipped iteration)")
    t_sh = tsub.add_parser("show", help="Ticket timeline + per-session token use and cost")
    t_sh.add_argument("id")
    t_us = tsub.add_parser("usage", help="Compute usage.json (tokens, duration, cost) from session transcripts")
    t_us.add_argument("id")
    t_sh = tsub.add_parser("share", help="Print the client link for a shipped cut (RECUT_PUBLIC_URL = base)")
    t_sh.add_argument("id")
    t_sh.add_argument("--session", type=int, help="default: the newest shipped iteration")
    t_sh.add_argument("--iteration", type=int)
    t_imp = tsub.add_parser("import-legacy", help="Import a pre-refactor session export as a baseline ticket")
    t_imp.add_argument("export_dir", type=pathlib.Path, help="e.g. recut-data/baseline/pre-refactor/<session>")
    t_imp.add_argument("--root", type=pathlib.Path, default=None,
                       help="tickets folder (default: the data repo's tickets, as other ticket commands)")
    t_imp.add_argument("--force", action="store_true", help="replace the ticket if it was already imported")
    t_r = tsub.add_parser("render", help="Render an iteration and print issues")
    t_r.add_argument("id")
    t_r.add_argument("--session", type=int)
    t_r.add_argument("--iteration", type=int)
    ticket_cmd.set_defaults(func=cmd_ticket)

    report_cmd = sub.add_parser("report", help="Numbers for the weekly improvement pass (reads only)")
    report_cmd.add_argument("--since", type=parse_date,
                            metavar="YYYY-MM-DD", help="only sessions started on or after this date")
    report_cmd.add_argument("--json", action="store_true", help="print one JSON object (for agents)")
    report_cmd.add_argument("--root", type=pathlib.Path, default=TICKETS_DIR,
                            help="tickets folder (default: .appdata/tickets)")
    report_cmd.add_argument("--html", action="store_true",
                            help="write one self-contained page for presenting (default recut-report.html)")
    report_cmd.add_argument("--out", type=pathlib.Path, default=None, help="with --html: output file")
    report_cmd.set_defaults(func=cmd_report)

    sync_cmd = sub.add_parser("sync", help="Commit + push ticket data to the data repo (recut-data)")
    sync_cmd.add_argument("-m", "--message")
    sync_cmd.add_argument("--quiet", action="store_true")
    sync_cmd.set_defaults(func=cmd_sync)

    serve_cmd = sub.add_parser("serve", help="Review server with live browser preview")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8000)
    serve_cmd.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    serve_cmd.set_defaults(func=cmd_serve)

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
