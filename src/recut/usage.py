"""Token use, duration and estimated cost of an agent session, from its Claude Code transcript.

`sessions/<n>/transcript.jsonl` (copied by the Stop hook) → `sessions/<n>/usage.json`:
`{model, models, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd,
duration_s, wall_s, turns}`. `model` is the one model that produced output, or "mixed" when the
session switched models; `models` has the per-model breakdown. `duration_s` is active time: a gap
that ends at the operator's next prompt counts up to IDLE_CAP_S, so hours the session sat waiting
for the operator don't count (a long tool run counts in full); `wall_s` is first-to-last entry. `cost_usd` is an estimate (null when any model used is not in PRICES_PER_MTOK).

The transcript format is not ours: unknown or broken lines are skipped, and an assistant message
that appears several times (streamed in parts) counts once, with its last-seen usage.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

IDLE_CAP_S = 300.0  # waiting longer than this for the operator's next prompt is idle time


# USD per million tokens, Anthropic first-party API list prices (source: Claude API pricing,
# as cached 2026-11-03). Update when prices change. Keys are substrings of the model id; the
# FIRST match wins, so specific versions come before family fallbacks. cache_write = 5-minute
# cache write (1.25x input); cache_read is 0.1x input unless the price sheet says otherwise.
# These are API-equivalent costs: on a Claude subscription the real cost is the plan, so treat
# cost_usd as a comparable effort measure across sessions and models, not as an invoice.
def _p(inp: float, out: float, read: Optional[float] = None) -> dict[str, float]:
    return {"input": inp, "output": out,
            "cache_read": read if read is not None else round(inp * 0.1, 4),
            "cache_write": round(inp * 1.25, 4)}


PRICES_PER_MTOK: dict[str, dict[str, float]] = {
    "fable-5-2": _p(8.0, 40.0, 0.20),
    "mythos-5-2": _p(8.0, 40.0, 0.20),
    "fable-5-1": _p(10.0, 50.0),
    "mythos-5-1": _p(10.0, 50.0),
    "fable-5": _p(10.0, 50.0),
    "opus-5-5": _p(4.0, 20.0, 0.20),
    "opus-5": _p(5.0, 25.0),
    "opus-4-8": _p(5.0, 25.0),
    "opus-4-7": _p(5.0, 25.0),
    "opus-4-6": _p(5.0, 25.0),
    "sonnet-5-5": _p(2.0, 10.0, 0.10),
    "sonnet-5": _p(2.0, 10.0),
    "sonnet-4-6": _p(3.0, 15.0),
    "haiku-5-5": _p(0.10, 0.50),  # prompts up to 100K tokens ($0.50 / $2.50 beyond)
    "haiku-4-5": _p(1.0, 5.0),
}


USAGE_FILE = "usage.json"
TRANSCRIPT_FILE = "transcript.jsonl"


def _price(model: Optional[str]) -> Optional[dict[str, float]]:
    name = (model or "").lower()
    for key, price in PRICES_PER_MTOK.items():
        if key in name:
            return price
    return None


def cost_usd(model: Optional[str], input_tokens: int, output_tokens: int,
             cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> Optional[float]:
    p = _price(model)
    if p is None:
        return None
    return (input_tokens * p["input"] + output_tokens * p["output"]
            + cache_read_tokens * p["cache_read"] + cache_write_tokens * p["cache_write"]) / 1e6


def _ts(value) -> Optional[float]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _int(v) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else 0


def _is_prompt(entry: dict) -> bool:
    """A user turn typed by a person (not a tool result, not a sidechain/meta message)."""
    if entry.get("type") != "user" or entry.get("isSidechain") or entry.get("isMeta"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in content)
    return False


def parse_transcript(text: str) -> dict:
    stamps: list[tuple[float, bool]] = []  # (time, entry is a typed prompt)
    turns = 0
    messages: dict[str, dict] = {}  # message id → {model, usage}; later entries replace earlier
    anon = 0
    for line in text.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        t = _ts(e["timestamp"]) if "timestamp" in e else None
        if t is not None:
            stamps.append((t, _is_prompt(e)))
        if _is_prompt(e):
            turns += 1
        msg = e.get("message")
        if e.get("type") == "assistant" and isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
            mid = msg.get("id")
            if not isinstance(mid, str):
                anon += 1
                mid = f"_anon{anon}"
            messages[mid] = {"model": msg.get("model"), "usage": msg["usage"]}

    models: dict[str, dict] = {}
    for m in messages.values():
        name = m["model"] if isinstance(m["model"], str) else "unknown"
        if name == "<synthetic>":
            continue
        u = m["usage"]
        acc = models.setdefault(name, {"input_tokens": 0, "output_tokens": 0,
                                       "cache_read_tokens": 0, "cache_write_tokens": 0})
        acc["input_tokens"] += _int(u.get("input_tokens"))
        acc["output_tokens"] += _int(u.get("output_tokens"))
        acc["cache_read_tokens"] += _int(u.get("cache_read_input_tokens"))
        acc["cache_write_tokens"] += _int(u.get("cache_creation_input_tokens"))
    costs = []
    stamps.sort()
    producers = [n for n, a in models.items() if a["output_tokens"] > 0] or list(models)
    for name, acc in models.items():
        c = cost_usd(name, **acc)
        acc["cost_usd"] = round(c, 4) if c is not None else None
        costs.append(c)
    total = {k: sum(a[k] for a in models.values())
             for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")}
    return {
        "model": (producers[0] if len(producers) == 1 else "mixed") if producers else None,
        "models": models,
        **total,
        "cost_usd": (round(sum(costs), 4) if costs and all(c is not None for c in costs) else None),
        # a gap that ends at a typed prompt was the agent waiting for the operator: capped
        "duration_s": round(sum(min(b - a, IDLE_CAP_S) if prompt else b - a
                                for (a, _), (b, prompt) in zip(stamps, stamps[1:])), 1),
        "wall_s": round(stamps[-1][0] - stamps[0][0], 1) if stamps else 0.0,
        "turns": turns,
    }


def write_usage(session_dir: Path) -> Optional[dict]:
    """Compute usage.json from the session's transcript. None when there is no transcript."""
    tp = session_dir / TRANSCRIPT_FILE
    if not tp.exists():
        return None
    data = parse_transcript(tp.read_text(errors="replace"))
    out = session_dir / USAGE_FILE
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(out)
    return data


def load_usage(session_dir: Path) -> Optional[dict]:
    p = session_dir / USAGE_FILE
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def refresh_stale(root: Path, ticket_id: Optional[str] = None) -> list[Path]:
    """(Re)compute usage.json for every session whose transcript is newer than it (or has none,
    or one in the older format)."""
    done = []
    pattern = f"{ticket_id}/sessions/*" if ticket_id else "*/sessions/*"
    for sd in sorted(root.glob(pattern)):
        tp, up = sd / TRANSCRIPT_FILE, sd / USAGE_FILE
        if tp.exists() and (not up.exists() or up.stat().st_mtime < tp.stat().st_mtime
                            or "wall_s" not in (load_usage(sd) or {})):  # written before active time
            if write_usage(sd) is not None:
                done.append(sd)
    return done
