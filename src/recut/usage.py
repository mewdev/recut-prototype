"""Token use, duration and estimated cost of an agent session, from its Claude Code transcript.

`sessions/<n>/transcript.jsonl` (copied by the Stop hook) → `sessions/<n>/usage.json`:
`{model, models, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd,
duration_s, turns}`. `model` is the model that produced most output; `models` has the per-model
breakdown. `cost_usd` is an estimate (null when any model used is not in PRICES_PER_MTOK).

The transcript format is not ours: unknown or broken lines are skipped, and an assistant message
that appears several times (streamed in parts) counts once, with its last-seen usage.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

# USD per million tokens. Keyed by a substring of the model name (first match wins).
# update when prices change; source: Anthropic pricing page
PRICES_PER_MTOK: dict[str, dict[str, float]] = {
    "opus": {"input": 5.0, "output": 25.0, "cache_read": 0.50, "cache_write": 6.25},
    "sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "haiku": {"input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_write": 1.25},
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
    stamps: list[float] = []
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
            stamps.append(t)
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
    for name, acc in models.items():
        c = cost_usd(name, **acc)
        acc["cost_usd"] = round(c, 4) if c is not None else None
        costs.append(c)
    total = {k: sum(a[k] for a in models.values())
             for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")}
    return {
        "model": max(models, key=lambda m: models[m]["output_tokens"]) if models else None,
        "models": models,
        **total,
        "cost_usd": (round(sum(costs), 4) if costs and all(c is not None for c in costs) else None),
        "duration_s": round(max(stamps) - min(stamps), 1) if len(stamps) > 1 else 0.0,
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
    """(Re)compute usage.json for every session whose transcript is newer than it (or has none)."""
    done = []
    pattern = f"{ticket_id}/sessions/*" if ticket_id else "*/sessions/*"
    for sd in sorted(root.glob(pattern)):
        tp, up = sd / TRANSCRIPT_FILE, sd / USAGE_FILE
        if tp.exists() and (not up.exists() or up.stat().st_mtime < tp.stat().st_mtime):
            if write_usage(sd) is not None:
                done.append(sd)
    return done
