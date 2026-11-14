"""`recut report --html`: one self-contained page for presenting results (L2).

No external requests: inline CSS, hand-drawn inline SVG, no scripts. Light/dark via prefers-color-scheme.
Input is the dict from `report.build` (its `overview` plus `failure_tags`). Every number shows its n and
metrics with n < MIN_N are tagged "too few to judge". Client quotes are feedback notes only: no names,
contacts, ticket ids or request text.
"""

from __future__ import annotations

from html import escape
from typing import Optional

from recut.report_v2 import MIN_N, fmt_dur, fmt_usd, fmt_value

CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#1c1b19;--mute:#6b6862;--line:#e3e0d9;--a:#2f6fb2;--b:#c9812a;--c:#2f8f6b;
--bar:#c4cfdd;--warn:#9a6a14}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#151514;--card:#201f1d;--ink:#eeece7;
--mute:#a09c93;--line:#34322e;--a:#6aa6e3;--b:#e0a458;--c:#5cc29a;--bar:#3a4656;--warn:#e0b45a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.05rem;margin:32px 0 10px}
.sub{color:var(--mute);margin:0 0 20px;font-size:.9rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.tile .v{font-size:2rem;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums}
.tile .l{font-size:.85rem;margin-top:4px}.tile .n{font-size:.75rem;color:var(--mute);margin-top:2px}
.tile .n.few{color:var(--warn)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:700px){.cols{grid-template-columns:1fr}.tile .v{font-size:1.7rem}}
svg{display:block;width:100%;height:auto}
svg text{fill:var(--mute);font:12.5px system-ui,sans-serif}
svg .bar{fill:var(--bar)}svg .ba{fill:var(--a)}svg .ax{stroke:var(--line);stroke-width:1}
svg .la{stroke:var(--a);fill:none;stroke-width:2}svg .lc{stroke:var(--c);fill:none;stroke-width:2}
svg .da{fill:var(--a)}svg .dc{fill:var(--c)}svg .hollow{fill:var(--card)}
svg .val{fill:var(--ink);font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:.8rem;color:var(--mute);margin-top:6px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mute);font-weight:600;font-size:.8rem}td.f,.few{color:var(--warn)}
.tw{overflow-x:auto}
blockquote{margin:0 0 10px;padding:8px 12px;border-left:3px solid var(--a);background:var(--card);border-radius:0 8px 8px 0}
blockquote small{display:block;color:var(--mute);margin-top:2px}
footer{margin-top:32px;color:var(--mute);font-size:.8rem}
"""


def _fmt(m: dict, kind: str) -> tuple[str, str]:
    """(big value, small n line) for a tile."""
    if m["value"] is None:
        return "-", f"n={m['n']}"
    n = f"{m['num']}/{m['n']}, n={m['n']}" if kind == "pct" else f"n={m['n']}"
    return fmt_value(m, kind), n


def _tile(label: str, m: dict, kind: str) -> str:
    v, n = _fmt(m, kind)
    few = m["n"] < MIN_N
    note = n + (" · too few to judge" if few else "")
    return (f'<div class="tile"><div class="v">{escape(v)}</div><div class="l">{escape(label)}</div>'
            f'<div class="n{" few" if few else ""}">{escape(note)}</div></div>')


def _weekly_chart(rows: list[dict]) -> str:
    if not rows:
        return '<p class="sub">No ticket-system tickets yet.</p>'
    w, h, pl, pr, pt, pb = 480, 250, 30, 40, 18, 34
    pw, ph = w - pl - pr, h - pt - pb
    top = max(max(r["tickets"] for r in rows), 1)
    step = pw / len(rows)
    y = lambda frac: pt + ph * (1 - frac)  # noqa: E731
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Tickets per week with ship rate and client approval">']
    for frac in (0, .5, 1):
        out.append(f'<line class="ax" x1="{pl}" x2="{w - pr}" y1="{y(frac):.1f}" y2="{y(frac):.1f}"/>')
        out.append(f'<text x="{pl - 6}" y="{y(frac) + 4:.1f}" text-anchor="end">{round(top * frac)}</text>')
        out.append(f'<text x="{w - pr + 6}" y="{y(frac) + 4:.1f}">{round(100 * frac)}%</text>')
    lines: dict[str, list[tuple[float, float, bool]]] = {"la": [], "lc": []}
    for i, r in enumerate(rows):
        cx = pl + step * (i + .5)
        bw = min(step * .5, 56)
        bh = ph * r["tickets"] / top
        out.append(f'<rect class="bar" x="{cx - bw / 2:.1f}" y="{pt + ph - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}"/>')
        out.append(f'<text class="val" x="{cx:.1f}" y="{pt + ph - bh - 4:.1f}" text-anchor="middle">{r["tickets"]}</text>')
        out.append(f'<text x="{cx:.1f}" y="{h - 12}" text-anchor="middle">{escape(r["week"])}</text>')
        for cls, key in (("la", "ship_rate"), ("lc", "client_approval")):
            m = r[key]
            if m["value"] is not None:
                lines[cls].append((cx, y(m["value"] / 100), m["n"] < MIN_N))
    for cls, pts in lines.items():
        if len(pts) > 1:
            out.append(f'<polyline class="{cls}" points="{" ".join(f"{x:.1f},{yy:.1f}" for x, yy, _ in pts)}"/>')
        for x, yy, few in pts:
            dot = "da" if cls == "la" else "dc"
            out.append(f'<circle class="{cls if few else dot}{" hollow" if few else ""}" cx="{x:.1f}" cy="{yy:.1f}" r="4.5"/>')
    out.append("</svg>")
    out.append('<div class="legend"><span><i style="background:var(--bar)"></i>tickets created (left axis)</span>'
               '<span><i style="background:var(--a)"></i>ship rate (right axis)</span>'
               '<span><i style="background:var(--c)"></i>client approval (right axis)</span>'
               f'<span>hollow dot = n &lt; {MIN_N}, too few to judge</span></div>')
    return "".join(out)


def _hbars(items: list[tuple[str, float]], fmt=lambda v: str(int(v))) -> str:
    if not items:
        return '<p class="sub">Nothing yet.</p>'
    lw, w, rh = 112, 380, 28
    top = max(v for _, v in items) or 1
    out = [f'<svg viewBox="0 0 {w} {rh * len(items) + 4}" role="img">']
    for i, (label, v) in enumerate(items):
        yy = i * rh + 2
        bw = (w - lw - 50) * v / top
        out.append(f'<text x="{lw - 8}" y="{yy + 16}" text-anchor="end">{escape(label)}</text>')
        out.append(f'<rect class="ba" x="{lw}" y="{yy + 3}" width="{max(bw, 2):.1f}" height="{rh - 8}" rx="3"/>')
        out.append(f'<text class="val" x="{lw + max(bw, 2) + 6:.1f}" y="{yy + 16}">{escape(fmt(v))}</text>')
    out.append("</svg>")
    return "".join(out)


def _rounds_chart(dist: dict) -> str:
    items = [(f"{k} round{'s' if k != '1' else ''}", float(v)) for k, v in dist["shipped"].items()]
    if dist["not_shipped"]:
        items.append(("not shipped yet", float(dist["not_shipped"])))
    return _hbars(items)


def _compare(o: dict) -> str:
    from recut.report_v2 import HEADLINE_ROWS, fmt_metric

    b, s = o["baseline"], o["system"]
    rows = [f"<tr><td>tickets</td><td>{b['tickets']}</td><td>{s['tickets']}</td></tr>"]
    for label, key, kind in HEADLINE_ROWS[:5]:
        cells = []
        for h in (b, s):
            txt = fmt_metric(h[key], kind)
            cells.append(f'<td class="{"f" if h[key]["n"] < MIN_N else ""}">{escape(txt)}</td>')
        rows.append(f"<tr><td>{escape(label)}</td>{''.join(cells)}</tr>")
    return ('<div class="tw"><table><tr><th></th><th>baseline (pre-refactor)</th><th>ticket system</th></tr>'
            + "".join(rows) + "</table></div>")


def _quotes(qs: list[dict]) -> str:
    if not qs:
        return '<p class="sub">No client comments logged yet.</p>'
    out = []
    for q in qs:
        stars = f"{'★' * q['rating']}{'☆' * (5 - q['rating'])} · " if q.get("rating") else ""
        who = "client approved" if q["decision"] == "approved" else "client asked for changes"
        out.append(f"<blockquote>{escape(q['text'])}<small>{stars}{who}</small></blockquote>")
    return "".join(out)


def render_html(data: dict, generated: Optional[str] = None) -> str:
    o = data["overview"]
    h = o["headline"]
    c = o["cost"]
    tiles = [
        _tile("real tickets", {"value": h["tickets"], "n": h["tickets"]}, "num"),
        _tile("shipped (of reviewed)", {"value": h["ship_rate"]["value"], "num": h["ship_rate"]["num"],
                                        "n": h["ship_rate"]["n"]}, "pct"),
        _tile("client approval (last reaction)", h["client_approval"], "pct"),
        _tile("average client rating", h["client_rating"], "stars"),
        _tile("shipped on first attempt", h["first_attempt_ship"], "pct"),
        _tile("median review rounds to ship", h["rounds_to_ship"], "num"),
        _tile("median turnaround to ship", h["turnaround_ship_s"], "dur"),
        _tile("median turnaround to client approval", h["turnaround_approved_s"], "dur"),
        _tile("median cost per shipped ticket*", h["cost_per_shipped_usd"], "usd"),
    ]
    tags = [(t["tag"], float(t["count"])) for t in data.get("failure_tags", [])[:8]]
    rng = o["range"]
    span = f"{rng['from']} to {rng['to']}" if rng["from"] else "no data"
    foot = (f"Data: tickets created {escape(span)}; n={h['tickets']} real tickets "
            f"({o['baseline']['tickets']} baseline, {o['system']['tickets']} ticket system); "
            f"{o['demo_excluded']} demo ticket(s) excluded. Metrics with n &lt; {MIN_N} are marked "
            f"&ldquo;too few to judge&rdquo;; nothing is extrapolated. "
            f"*Costs are API-equivalent estimates ({escape(fmt_usd(c['total_usd']))} total, "
            f"agent time {escape(fmt_dur(c['duration_s']))}), not invoices; baseline has no turnaround or cost data. "
            f"Weekly trend: ISO week of ticket creation, ticket system only.")
    if generated:
        foot += f" Generated {escape(generated)}."
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>recut results</title><style>{CSS}</style></head>
<body><main>
<h1>recut results</h1>
<p class="sub">Music cutting with an agent and a human review loop. Honest numbers: every rate shows its n.</p>
<div class="tiles">{"".join(tiles)}</div>
<h2>Weekly trend</h2><div class="card">{_weekly_chart(o["weekly"])}</div>
<div class="cols">
<div><h2>Review rounds until ship</h2><div class="card">{_rounds_chart(o["rounds_distribution"])}</div></div>
<div><h2>Top failure tags</h2><div class="card">{_hbars(tags)}</div></div>
</div>
<h2>Baseline vs ticket system</h2><div class="card">{_compare(o)}</div>
<h2>What clients said</h2>{_quotes(o["quotes"])}
<footer>{foot}</footer>
</main></body></html>
"""
