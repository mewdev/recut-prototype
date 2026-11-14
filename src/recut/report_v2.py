"""`recut report` overview (L2): headline numbers, turnaround, cost, baseline vs ticket system, weekly trend.

Honesty rules (docs/PLAN.md §3.7): demo tickets (session agent `demo`) are never counted; every rate carries
its `n`; a metric with n < MIN_N is flagged "too few to judge"; nothing is extrapolated.

Definitions (per real ticket):
- baseline = imported pre-refactor ticket (session agent `legacy-pre-refactor`); everything else is the ticket system.
  Baseline timestamps are dates only, so baseline tickets are left out of turnaround and cost.
- shipped = any iteration has a `ship` review. Ship rate = shipped / tickets with any review.
- first-attempt ship = the first reviewed iteration of the first session is `ship`.
- review rounds to ship = reviewed iterations (all sessions, in order) up to and including the first `ship`.
- turnaround from the ticket timeline: created -> first (successful) render, -> first ship, ship -> first client
  answer, created -> first client approval. Missing events (old tickets) are left out, never guessed.
- client approval = last reaction approved / tickets with any reaction.
- cost = API-equivalent estimate from sessions' usage.json (not an invoice); sessions without it are listed.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from recut import tickets, usage

MIN_N = 5
BASELINE_AGENT = "legacy-pre-refactor"


def _dt(text) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class _Ticket:
    def __init__(self, tid: str, root: Path):
        self.id = tid
        req = tickets.load_request(tid, root)
        self.created = self.t_created = _dt(req.created_at)
        self.sessions: list[dict] = []
        self.reviews: list[tuple[int, int, str]] = []  # (session, iteration, verdict) in order
        for n in tickets.session_numbers(tid, root):
            sd = tickets.session_dir(tid, n, root)
            try:
                meta = json.loads((sd / "meta.json").read_text())
            except (OSError, ValueError):
                meta = {}
            self.sessions.append({"n": n, "agent": meta.get("agent"), "model": meta.get("model"),
                                  "usage": usage.load_usage(sd)})
            for k in tickets.iteration_numbers(tid, n, root):
                rv = tickets.load_iteration_review(tid, n, k, root)
                if rv is not None:
                    self.reviews.append((n, k, rv.verdict))
        self.baseline = any(s["agent"] == BASELINE_AGENT for s in self.sessions)
        self.feedback = tickets.load_client_feedback(tid, root)
        events = tickets.ticket_timeline(tid, root)
        self.t_render = next((_dt(e["ts"]) for e in events
                              if e["op"] == "rendered" and not e.get("error")), None)
        self.t_ship = next((_dt(e["ts"]) for e in events if e["op"] == "shipped"), None)
        self.t_answer = next((_dt(e["ts"]) for e in events if e["op"] == "client_feedback"
                              and self.t_ship is not None and _dt(e["ts"]) >= self.t_ship), None)
        self.t_approved = next((_dt(e["ts"]) for e in events if e["op"] == "client_feedback"
                                and e.get("decision") == "approved"), None)

    @property
    def shipped(self) -> bool:
        return any(v == "ship" for _, _, v in self.reviews)

    @property
    def rounds_to_ship(self) -> Optional[int]:
        for i, (_, _, v) in enumerate(self.reviews, 1):
            if v == "ship":
                return i
        return None

    def secs(self, a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
        if self.baseline or a is None or b is None:
            return None
        return max(0.0, (b - a).total_seconds())

    @property
    def cost(self) -> Optional[float]:
        known = [s["usage"]["cost_usd"] for s in self.sessions
                 if s["usage"] and s["usage"].get("cost_usd") is not None]
        return sum(known) if known and not self.baseline else None

    @property
    def week(self) -> str:
        y, w, _ = (self.created or datetime.now(timezone.utc)).isocalendar()
        return f"{y}-W{w:02d}"


def load_tickets(root: Path, since: Optional[date] = None) -> tuple[list[_Ticket], int]:
    """Real tickets (demos left out) and the number of demo tickets skipped."""
    out: list[_Ticket] = []
    demos = 0
    for req in sorted(tickets.list_tickets(root), key=lambda r: (r.created_at, r.id)):
        if tickets.is_demo(req.id, root):
            demos += 1
            continue
        t = _Ticket(req.id, root)
        if since is not None and (t.created is None or t.created.date() < since):
            continue
        out.append(t)
    return out, demos


# ---- metric helpers -------------------------------------------------------------------


def _rate(num: int, den: int) -> dict:
    return {"value": round(100 * num / den, 1) if den else None, "num": num, "n": den}


def _median(vals: list[float]) -> dict:
    return {"value": float(statistics.median(vals)) if vals else None, "n": len(vals)}


def _p90(vals: list[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    return float(s[max(0, math.ceil(0.9 * len(s)) - 1)])


def _spread(vals: list[float]) -> dict:
    return {**_median(vals), "p90": _p90(vals)}


def headline(ts: list[_Ticket]) -> dict:
    reviewed = [t for t in ts if t.reviews]
    shipped = [t for t in ts if t.shipped]
    with_fb = [t for t in ts if t.feedback]
    ratings = [fb.rating for t in ts for fb in t.feedback if fb.rating is not None]
    first = [t.reviews[0][2] for t in reviewed]
    costs = [t.cost for t in shipped if t.cost is not None]
    return {
        "tickets": len(ts),
        "reviewed": len(reviewed),
        "shipped": {"value": len(shipped), "n": len(ts)},
        "ship_rate": _rate(len(shipped), len(reviewed)),
        "first_attempt_ship": _rate(sum(1 for v in first if v == "ship"), len(first)),
        "client_approval": _rate(sum(1 for t in with_fb if t.feedback[-1].decision == "approved"), len(with_fb)),
        "client_rating": {"value": round(statistics.fmean(ratings), 2) if ratings else None, "n": len(ratings)},
        "rounds_to_ship": _median([t.rounds_to_ship for t in shipped]),
        "turnaround_ship_s": _median([x for t in ts if (x := t.secs(t.created, t.t_ship)) is not None]),
        "turnaround_approved_s": _median([x for t in ts if (x := t.secs(t.created, t.t_approved)) is not None]),
        "cost_per_shipped_usd": _median(costs),
    }


def turnaround(ts: list[_Ticket]) -> dict:
    def col(a: str, b: str) -> dict:
        return _spread([x for t in ts if (x := t.secs(getattr(t, a), getattr(t, b))) is not None])

    return {"created_to_first_render": col("t_created", "t_render"),
            "created_to_first_ship": col("t_created", "t_ship"),
            "ship_to_client_answer": col("t_ship", "t_answer"),
            "created_to_client_approved": col("t_created", "t_approved")}


def _model_row() -> dict:
    return {"sessions": 0, "duration_s": 0.0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.0}


def cost(ts: list[_Ticket]) -> dict:
    ts = [t for t in ts if not t.baseline]
    models: dict[str, dict] = {}
    keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    totals = dict.fromkeys(keys, 0)
    total_cost = duration = 0.0
    sessions_with = cost_unknown = 0
    missing: list[str] = []
    per_ticket: list[float] = []
    for t in ts:
        for s in t.sessions:
            u = s["usage"]
            if not u:
                missing.append(f"{t.id} s{s['n']}")
                continue
            sessions_with += 1
            duration += u.get("duration_s") or 0.0
            for k in keys:
                totals[k] += u.get(k) or 0
            if u.get("cost_usd") is None:
                cost_unknown += 1
            else:
                total_cost += u["cost_usd"]
            main = models.setdefault(u.get("model") or s["model"] or "unknown", _model_row())
            main["sessions"] += 1
            main["duration_s"] += u.get("duration_s") or 0.0
            for name, m in (u.get("models") or {}).items():
                row = models.setdefault(name, _model_row())
                for k in keys:
                    row[k] += m.get(k) or 0
                row["cost_usd"] += m.get("cost_usd") or 0.0
        if t.cost is not None:
            per_ticket.append(t.cost)
    return {
        "label": "API-equivalent estimate, not an invoice",
        "sessions_with_usage": sessions_with, "cost_unknown_sessions": cost_unknown,
        "total_usd": round(total_cost, 2), "duration_s": round(duration, 1), **totals,
        "per_ticket_usd": {**_median(per_ticket),
                           "mean": round(statistics.fmean(per_ticket), 2) if per_ticket else None},
        "per_model": [{"model": m, **{k: (round(v, 2) if k == "cost_usd" else v) for k, v in r.items()}}
                      for m, r in sorted(models.items())],
        "no_usage_data": missing,
    }


def weekly(ts: list[_Ticket]) -> list[dict]:
    out = []
    for week in sorted({t.week for t in ts}):
        h = headline([t for t in ts if t.week == week])
        out.append({"week": week, "tickets": h["tickets"], "ship_rate": h["ship_rate"],
                    "client_approval": h["client_approval"], "rounds_to_ship": h["rounds_to_ship"]})
    return out


def rounds_distribution(ts: list[_Ticket]) -> dict:
    c = Counter(t.rounds_to_ship for t in ts if t.shipped)
    return {"shipped": {str(k): c[k] for k in sorted(c)},
            "not_shipped": sum(1 for t in ts if t.reviews and not t.shipped)}


def quotes(ts: list[_Ticket], limit: int = 3) -> list[dict]:
    """Client feedback notes (verbatim), approved + best-rated first. No ticket ids, names or request text."""
    items = [(fb.decision == "approved", fb.rating or 0, fb.at, fb.note.strip(), fb.rating, fb.decision)
             for t in ts for fb in t.feedback if fb.note and fb.note.strip()]
    items.sort(key=lambda x: x[:3], reverse=True)
    return [{"text": text, "rating": rating, "decision": decision} for *_, text, rating, decision in items[:limit]]


def build_overview(root: Path, since: Optional[date] = None) -> dict:
    ts, demos = load_tickets(root, since)
    base = [t for t in ts if t.baseline]
    system = [t for t in ts if not t.baseline]
    stamps = [t.created for t in ts if t.created]
    return {
        "min_n": MIN_N,
        "demo_excluded": demos,
        "range": {"from": min(stamps).date().isoformat() if stamps else None,
                  "to": max(stamps).date().isoformat() if stamps else None},
        "headline": headline(ts),
        "baseline": headline(base),
        "system": headline(system),
        "turnaround": turnaround(ts),
        "cost": cost(ts),
        "weekly": weekly(system),
        "rounds_distribution": rounds_distribution(ts),
        "quotes": quotes(ts),
    }


# ---- text -----------------------------------------------------------------------------


def fmt_dur(s: Optional[float]) -> str:
    if s is None:
        return "-"
    if s < 90:
        return f"{s:.0f} s"
    if s < 5400:
        return f"{s / 60:.0f} min"
    if s < 2 * 86400:
        return f"{s / 3600:.1f} h"
    return f"{s / 86400:.1f} d"


def fmt_usd(v: Optional[float]) -> str:
    return "-" if v is None else f"${v:,.2f}"


def fmt_value(m: dict, kind: str) -> str:
    v = m["value"]
    if v is None:
        return "-"
    return {"pct": f"{v:.0f}%", "dur": fmt_dur(v), "usd": fmt_usd(v), "stars": f"{v:.1f}/5",
            "num": (str(int(v)) if float(v).is_integer() else f"{v:.1f}")}[kind]


def fmt_metric(m: dict, kind: str) -> str:
    """'67% (4/6, n=6)' / '3.5 h (n=2, too few to judge)' / '- (n=0, no data)'."""
    if m["value"] is None:
        return f"- (n={m['n']}, no data)"
    s = fmt_value(m, kind)
    s += f" ({m['num']}/{m['n']}, n={m['n']}" if kind == "pct" else f" (n={m['n']}"
    return s + (", too few to judge)" if m["n"] < MIN_N else ")")


HEADLINE_ROWS = [("ship rate", "ship_rate", "pct"),
                 ("first-attempt ship rate", "first_attempt_ship", "pct"),
                 ("client approval (last reaction)", "client_approval", "pct"),
                 ("average client rating", "client_rating", "stars"),
                 ("median review rounds to ship", "rounds_to_ship", "num"),
                 ("median turnaround created -> shipped", "turnaround_ship_s", "dur"),
                 ("median turnaround created -> client approved", "turnaround_approved_s", "dur"),
                 ("median cost per shipped ticket (API-equivalent)", "cost_per_shipped_usd", "usd")]


def format_overview(o: dict) -> list[str]:
    h = o["headline"]
    out = [f"Headline: {h['tickets']} real tickets ({o['baseline']['tickets']} baseline, "
           f"{o['system']['tickets']} ticket system), {o['demo_excluded']} demo excluded; "
           f"{h['shipped']['value']} shipped, {h['reviewed']} reviewed. "
           f"Rates show n; n < {o['min_n']} = too few to judge."]
    w = max(len(r[0]) for r in HEADLINE_ROWS)
    for label, key, kind in HEADLINE_ROWS:
        out.append(f"   {label:<{w}}  {fmt_metric(h[key], kind)}")
    if o["range"]["from"]:
        out.append(f"   data: tickets created {o['range']['from']} .. {o['range']['to']}")

    out += ["", "Turnaround (ticket system only; tickets lacking an event are left out)"]
    names = {"created_to_first_render": "created -> first render", "created_to_first_ship": "created -> first ship",
             "ship_to_client_answer": "ship -> client answer",
             "created_to_client_approved": "created -> client approved"}
    for key, label in names.items():
        m = o["turnaround"][key]
        out.append(f"   {label:<27} median {fmt_metric(m, 'dur')}, p90 {fmt_dur(m['p90'])}")

    c = o["cost"]
    out += ["", f"Cost ({c['label']}; ticket system only)",
            f"   total {fmt_usd(c['total_usd'])} over {c['sessions_with_usage']} sessions with usage; "
            f"per ticket median {fmt_metric(c['per_ticket_usd'], 'usd')}, mean {fmt_usd(c['per_ticket_usd']['mean'])}",
            f"   tokens: in {c['input_tokens']:,}, out {c['output_tokens']:,}, cache read {c['cache_read_tokens']:,}, "
            f"cache write {c['cache_write_tokens']:,}; agent time {fmt_dur(c['duration_s'])}"
            + (f"; {c['cost_unknown_sessions']} sessions with unpriced model" if c["cost_unknown_sessions"] else "")]
    for m in c["per_model"]:
        out.append(f"   model {m['model']}: {fmt_usd(m['cost_usd'])}, out {m['output_tokens']:,} tokens, "
                   f"{m['sessions']} sessions as main model, {fmt_dur(m['duration_s'])}")
    out.append("   no usage data: " + (", ".join(c["no_usage_data"]) if c["no_usage_data"] else "none"))

    out += ["", "Baseline (pre-refactor) vs ticket system"]
    b, s = o["baseline"], o["system"]
    out.append(f"   {'':<46}  {'baseline (pre-refactor)':<34}  ticket system")
    out.append(f"   {'tickets':<46}  {b['tickets']:<34}  {s['tickets']}")
    for label, key, kind in HEADLINE_ROWS[:5]:
        out.append(f"   {label:<46}  {fmt_metric(b[key], kind):<34}  {fmt_metric(s[key], kind)}")
    out.append("   (baseline timestamps are dates only: no turnaround or cost for it)")

    out += ["", "Weekly trend (ISO week of ticket creation, ticket system)"]
    if not o["weekly"]:
        out.append("   none")
    for r in o["weekly"]:
        out.append(f"   {r['week']}  tickets {r['tickets']}  ship {fmt_metric(r['ship_rate'], 'pct')}  "
                   f"client approval {fmt_metric(r['client_approval'], 'pct')}  "
                   f"median rounds {fmt_metric(r['rounds_to_ship'], 'num')}")
    return out
