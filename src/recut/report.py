"""`recut report`: the numbers the weekly improvement pass works from (docs/IMPROVEMENT_LOOP.md).

Reads every ticket under a tickets root and never writes. Definitions: docs/workstreams/B-backend.md (B7).
- A session's result is the verdict of its highest reviewed iteration; no review = unreviewed (left out of rates).
- Iterations to ship: the iteration k of the session's first `ship` review.
- Multi-song: the session's latest iteration plan has more than one source.
- Model: sessions/<n>/meta.json `model`.
- Client feedback (`client_feedback.jsonl`, `recut ticket client`): only reactions on sessions in scope.
  Approval rate = tickets whose LAST reaction is approved / tickets with any reaction; rounds = `changes`
  before the first `approved`; agreement = operator verdict on that iteration vs the client decision
  (ship <-> approved, fixable/reject <-> changes).
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from recut import tickets
from recut.contracts import Review
from recut.paths import TICKETS_DIR

GUI_BASE = "http://localhost:8000/t/"
WORST_N = 5
TAG_GROUPS: dict[str, tuple[str, ...]] = {
    "analysis": ("map_wrong",),
    "engine": ("missing_primitive", "artifact", "fx_wrong"),
    "validator-catchable": ("off_beat", "harmonic_clash", "abrupt", "duration_miss"),
    "judgement": ("intent_misread", "wrong_section", "energy_drop", "bad_ending"),
}
TAG_GROUP = {t: g for g, ts in TAG_GROUPS.items() for t in ts}


def parse_date(text: str) -> date:
    """argparse type for --since (YYYY-MM-DD)."""
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {text!r}") from None


def _read_json(p: Path) -> Optional[dict]:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None



def _used_sources(plan: Optional[dict]) -> set[str]:
    """Sources that clips actually use: a plan may declare sources it doesn't cut from."""
    used = set()
    for track in (plan or {}).get("tracks", []):
        for node in track.get("clips", []):
            if node.get("type") == "clip" and node.get("source"):
                used.add(node["source"])
    return used

class _Session:
    """One reviewed or unreviewed agent session, with everything the report needs from it."""

    def __init__(self, ticket_id: str, n: int, model: Optional[str], multi_song: bool,
                 reviews: dict[int, Review], renders: dict[int, Optional[dict]]):
        self.ticket_id = ticket_id
        self.n = n
        self.model = model or "unknown"
        self.multi_song = multi_song
        self.reviews = reviews  # iteration k -> its review (reviewed iterations only)
        self.renders = renders  # iteration k -> render.json (None when missing)

    @property
    def reviewed(self) -> bool:
        return bool(self.reviews)

    @property
    def result(self) -> Optional[str]:
        return self.reviews[max(self.reviews)].verdict if self.reviews else None

    @property
    def first_ship(self) -> Optional[int]:
        ks = [k for k in sorted(self.reviews) if self.reviews[k].verdict == "ship"]
        return ks[0] if ks else None

    @property
    def without_ship(self) -> int:
        return sum(1 for r in self.reviews.values() if r.verdict != "ship")

    @property
    def bad_splices(self) -> int:
        return sum(1 for r in self.reviews.values() for s in r.splices.values() if not s.ok)


def _load_sessions(root: Path, since: Optional[date]) -> tuple[list[_Session], int]:
    """All sessions in scope (started on/after `since`) and the number of tickets they belong to."""
    sessions: list[_Session] = []
    ticket_ids: set[str] = set()
    for req in tickets.list_tickets(root):
        tid = req.id
        for n in tickets.session_numbers(tid, root):
            sdir = tickets.session_dir(tid, n, root)
            meta = _read_json(sdir / "meta.json") or {}
            started = meta.get("started_at") or req.created_at
            if since is not None:
                try:
                    if datetime.fromisoformat(started).date() < since:
                        continue
                except ValueError:
                    continue
            ks = tickets.iteration_numbers(tid, n, root)
            reviews: dict[int, Review] = {}
            renders: dict[int, Optional[dict]] = {}
            for k in ks:
                idir = tickets.iteration_dir(tid, n, k, root)
                rv = tickets.load_iteration_review(tid, n, k, root)
                if rv is not None:
                    reviews[k] = rv
                    renders[k] = _read_json(idir / "render.json")
            latest_plan = next((_read_json(tickets.iteration_dir(tid, n, k, root) / "plan.json")
                                for k in reversed(ks)
                                if (tickets.iteration_dir(tid, n, k, root) / "plan.json").exists()), None)
            multi = len(_used_sources(latest_plan)) > 1
            sessions.append(_Session(tid, n, meta.get("model"), multi, reviews, renders))
            ticket_ids.add(tid)
    return sessions, len(ticket_ids)


def _rate_row(kind: str, group: str, sessions: list[_Session]) -> dict:
    n = len(sessions)
    results = Counter(s.result for s in sessions)
    shipped = [s.first_ship for s in sessions if s.result == "ship" and s.first_ship is not None]
    return {
        "kind": kind, "group": group, "n": n,
        "ship": results["ship"], "fixable": results["fixable"], "reject": results["reject"],
        "success_pct": round(100 * results["ship"] / n, 1) if n else None,
        "median_iterations_to_ship": float(statistics.median(shipped)) if shipped else None,
    }


def _success_rows(reviewed: list[_Session]) -> list[dict]:
    rows = [_rate_row("overall", "overall", reviewed)]
    for model in sorted({s.model for s in reviewed}):
        rows.append(_rate_row("model", model, [s for s in reviewed if s.model == model]))
    rows.append(_rate_row("shape", "single-song", [s for s in reviewed if not s.multi_song]))
    rows.append(_rate_row("shape", "multi-song", [s for s in reviewed if s.multi_song]))
    return rows


def _failure_tags(reviewed: list[_Session]) -> list[dict]:
    counts: Counter = Counter()
    for s in reviewed:
        for r in s.reviews.values():
            counts.update(r.tags)
            for sp in r.splices.values():
                counts.update(sp.tags)
    order = {g: i for i, g in enumerate(TAG_GROUPS)}
    rows = [{"tag": t, "group": TAG_GROUP.get(t, "other"), "count": c} for t, c in counts.items()]
    rows.sort(key=lambda r: (-r["count"], order.get(r["group"], len(order)), r["tag"]))
    return rows


def _splice_key(sid: str) -> tuple:
    return (len(sid), sid)


def _validator_misses(reviewed: list[_Session]) -> dict:
    """Bad splices (ok: false) with no render issue whose `splice` is that splice id."""
    items: list[dict] = []
    unrendered = 0
    for s in reviewed:
        for k in sorted(s.reviews):
            r = s.reviews[k]
            bad = [sid for sid in sorted(r.splices, key=_splice_key) if not r.splices[sid].ok]
            render = s.renders.get(k)
            if render is None:
                unrendered += len(bad)
                continue
            caught = {i.get("splice") for i in render.get("issues", []) if i.get("splice")}
            for sid in bad:
                if sid not in caught:
                    sp = r.splices[sid]
                    items.append({"ticket_id": s.ticket_id, "session": s.n, "iteration": k,
                                  "splice": sid, "tags": list(sp.tags), "note": sp.note})
    return {"count": len(items), "unrendered": unrendered, "items": items}


def _check_accuracy(reviewed: list[_Session]) -> list[dict]:
    """Per issue rule: flagged splices (one count per rule, splice and reviewed iteration) marked bad vs ok."""
    flagged: Counter = Counter()
    bad: Counter = Counter()
    ok: Counter = Counter()
    unrated: Counter = Counter()
    for s in reviewed:
        for k, r in s.reviews.items():
            render = s.renders.get(k)
            if render is None:
                continue
            pairs = {(i["rule"], i["splice"]) for i in render.get("issues", []) if i.get("splice")}
            for rule, sid in pairs:
                flagged[rule] += 1
                sp = r.splices.get(sid)
                if sp is None:
                    unrated[rule] += 1
                elif sp.ok:
                    ok[rule] += 1
                else:
                    bad[rule] += 1
    rows = []
    for rule in flagged:
        rated = bad[rule] + ok[rule]
        rows.append({"rule": rule, "flagged": flagged[rule], "bad": bad[rule], "ok": ok[rule],
                     "unrated": unrated[rule],
                     "precision_pct": round(100 * bad[rule] / rated, 1) if rated else None})
    rows.sort(key=lambda r: (-r["flagged"], r["rule"]))
    return rows


def _worst_sessions(reviewed: list[_Session]) -> list[dict]:
    ranked = sorted((s for s in reviewed if s.without_ship > 0),
                    key=lambda s: (-s.without_ship, -s.bad_splices, s.ticket_id, s.n))[:WORST_N]
    out = []
    for s in ranked:
        tags: Counter = Counter()
        notes: list[str] = []
        for k in sorted(s.reviews):
            r = s.reviews[k]
            tags.update(r.tags)
            if r.note:
                notes.append(f"s{s.n}·it{k}: {r.note}")
            for sid in sorted(r.splices, key=_splice_key):
                sp = r.splices[sid]
                tags.update(sp.tags)
                if sp.note:
                    notes.append(f"s{s.n}·it{k} {sid}: {sp.note}")
        out.append({"ticket_id": s.ticket_id, "session": s.n, "model": s.model, "result": s.result,
                    "iterations_without_ship": s.without_ship, "bad_splices": s.bad_splices,
                    "tags": dict(tags.most_common()), "notes": notes,
                    "url": GUI_BASE + s.ticket_id})
    return out


def _client_feedback(root: Path, sessions: list[_Session]) -> dict:
    """Client reactions on the sessions in scope (see the module docstring)."""
    in_scope = {(s.ticket_id, s.n) for s in sessions}
    feedback: dict[str, list] = {}
    for tid in dict.fromkeys(s.ticket_id for s in sessions):
        fbs = [fb for fb in tickets.load_client_feedback(tid, root) if (tid, fb.session) in in_scope]
        if fbs:
            feedback[tid] = fbs

    approved_last = 0
    rounds: list[int] = []
    ratings: list[int] = []
    change_requests: list[dict] = []
    compared = matched = unreviewed = entries = 0
    mismatches: list[dict] = []
    for tid, fbs in feedback.items():
        entries += len(fbs)
        if fbs[-1].decision == "approved":
            approved_last += 1
        first = next((i for i, fb in enumerate(fbs) if fb.decision == "approved"), None)
        if first is not None:
            rounds.append(first)  # every reaction before the first approval is a `changes`
        for fb in fbs:
            if fb.rating is not None:
                ratings.append(fb.rating)
            if fb.decision == "changes" and fb.note:
                change_requests.append({"ticket_id": tid, "session": fb.session, "iteration": fb.iteration,
                                        "rating": fb.rating, "note": fb.note})
            rv = tickets.load_iteration_review(tid, fb.session, fb.iteration, root)
            if rv is None:
                unreviewed += 1
                continue
            compared += 1
            if (rv.verdict == "ship") == (fb.decision == "approved"):
                matched += 1
            else:
                mismatches.append({"ticket_id": tid, "session": fb.session, "iteration": fb.iteration,
                                   "operator": rv.verdict, "client": fb.decision})

    n = len(feedback)
    return {
        "tickets": n,
        "entries": entries,
        "approval": {"approved": approved_last, "tickets": n,
                     "pct": round(100 * approved_last / n, 1) if n else None},
        "rounds": {"approved_tickets": len(rounds), "never_approved": n - len(rounds),
                   "median": float(statistics.median(rounds)) if rounds else None},
        "rating": {"rated": len(ratings),
                   "avg": round(statistics.fmean(ratings), 2) if ratings else None},
        "change_requests": change_requests,
        "agreement": {"compared": compared, "matched": matched, "unreviewed": unreviewed,
                      "pct": round(100 * matched / compared, 1) if compared else None,
                      "mismatches": mismatches},
    }


def build(root: Path = TICKETS_DIR, since: Optional[date] = None) -> dict:
    """The whole report as one JSON-serialisable dict (what `--json` prints)."""
    sessions, n_tickets = _load_sessions(root, since)
    reviewed = [s for s in sessions if s.reviewed]
    return {
        "since": since.isoformat() if since else None,
        "tickets": n_tickets,
        "sessions": {"total": len(sessions), "reviewed": len(reviewed),
                     "unreviewed": len(sessions) - len(reviewed)},
        "success": _success_rows(reviewed),
        "failure_tags": _failure_tags(reviewed),
        "validator_misses": _validator_misses(reviewed),
        "check_accuracy": _check_accuracy(reviewed),
        "worst_sessions": _worst_sessions(reviewed),
        "client": _client_feedback(root, sessions),
    }


# ---- text output ----------------------------------------------------------------------


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)] if rows else [len(h) for h in header]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*header).rstrip()]
    lines += [fmt.format(*r).rstrip() for r in rows]
    return ["   " + ln for ln in lines]


def _pct(v: Optional[float]) -> str:
    return "-" if v is None else f"{v:.0f}%"


def _num(v: Optional[float]) -> str:
    if v is None:
        return "-"
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def format_text(data: dict) -> str:
    sess = data["sessions"]
    head = (f"recut report: {data['tickets']} tickets, {sess['total']} sessions "
            f"({sess['reviewed']} reviewed, {sess['unreviewed']} unreviewed)")
    if data["since"]:
        head += f", started since {data['since']}"
    out = [head, "", "1. Success rate (reviewed sessions; success = result ship)"]
    rows = []
    for r in data["success"]:
        label = r["group"] if r["kind"] != "model" else f"model: {r['group']}"
        rows.append([label, str(r["n"]), str(r["ship"]), str(r["fixable"]), str(r["reject"]),
                     _pct(r["success_pct"]), _num(r["median_iterations_to_ship"])])
    out += _table(["group", "n", "ship", "fixable", "reject", "success", "median iters to ship"], rows)

    out += ["", "2. Failure tags (all reviewed iterations, splice + overall)"]
    if data["failure_tags"]:
        out += _table(["tag", "group", "count"],
                      [[t["tag"], t["group"], str(t["count"])] for t in data["failure_tags"]])
    else:
        out.append("   none")

    vm = data["validator_misses"]
    out += ["", f"3. Validator misses: {vm['count']} bad splices with no render issue on that splice"
                + (f" ({vm['unrendered']} bad splices in unrendered iterations skipped)" if vm["unrendered"] else "")]
    if vm["items"]:
        out += _table(["ticket", "session·iter", "splice", "tags", "note"],
                      [[i["ticket_id"], f"s{i['session']}·it{i['iteration']}", i["splice"],
                        ",".join(i["tags"]) or "-", i["note"] or ""] for i in vm["items"]])

    out += ["", "4. Worst sessions (most iterations without ship, then most bad splices)"]
    if not data["worst_sessions"]:
        out.append("   none")
    for i, w in enumerate(data["worst_sessions"], 1):
        out.append(f"   {i}. {w['ticket_id']} s{w['session']} model={w['model']} result={w['result']} "
                   f"without-ship={w['iterations_without_ship']} bad-splices={w['bad_splices']}")
        if w["tags"]:
            out.append("      tags: " + ", ".join(f"{t} x{c}" for t, c in w["tags"].items()))
        for note in w["notes"]:
            out.append(f"      note: {note}")
        out.append(f"      {w['url']}")

    out += ["", "5. Check accuracy (flagged splices marked bad vs ok; issues without a splice not counted)"]
    if data["check_accuracy"]:
        out += _table(["rule", "flagged", "bad", "ok", "unrated", "precision"],
                      [[c["rule"], str(c["flagged"]), str(c["bad"]), str(c["ok"]), str(c["unrated"]),
                        _pct(c["precision_pct"])] for c in data["check_accuracy"]])
    else:
        out.append("   none")

    cl = data["client"]
    out += ["", "6. Client feedback (approval = last reaction approved; agreement = operator verdict vs client)"]
    if not cl["tickets"]:
        out.append("   none yet: log with `recut ticket client <id> --approved | --changes`")
    else:
        ap, rd, rt, ag = cl["approval"], cl["rounds"], cl["rating"], cl["agreement"]
        out.append(f"   tickets: {cl['tickets']} · reactions: {cl['entries']} · "
                   f"client approval rate: {ap['approved']}/{ap['tickets']} ({_pct(ap['pct'])})")
        out.append(f"   rounds until approval: median {_num(rd['median'])} "
                   f"({rd['approved_tickets']} approved, {rd['never_approved']} not yet)")
        out.append(f"   average rating: {_num(rt['avg'])} ({rt['rated']} rated reactions)")
        out.append(f"   agreement with operator verdict: {ag['matched']}/{ag['compared']} ({_pct(ag['pct'])})"
                   + (f", {ag['unreviewed']} unreviewed" if ag["unreviewed"] else ""))
        if cl["change_requests"]:
            out.append("   change requests:")
            for c in cl["change_requests"]:
                stars = f" ★{c['rating']}" if c["rating"] else ""
                out.append(f"     {c['ticket_id']} s{c['session']}·it{c['iteration']}{stars}: {c['note']}")
        for m in ag["mismatches"]:
            out.append(f"   disagree: {m['ticket_id']} s{m['session']}·it{m['iteration']}: "
                       f"operator {m['operator']}, client {m['client']}")
    return "\n".join(out)
