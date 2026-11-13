#!/usr/bin/env bash
# Claude Code Stop hook: copy the session transcript into the recut ticket session, so the
# weekly improvement pass (docs/IMPROVEMENT_LOOP.md) can read how the agent reasoned.
#
# Claude Code runs this with a JSON object on stdin that includes "transcript_path". Where to
# copy to, in order:
#   1. $RECUT_SESSION (the session folder `recut ticket work` printed)
#   2. the folder named in <tickets root>/.current_session, which `recut ticket work` writes
#      (a hook can't see an `export` made inside the agent's shell)
# <tickets root> is $RECUT_TICKETS_DIR, else $RECUT_HOME/.appdata/tickets, else
# <repo>/.appdata/tickets. Test override: $RECUT_TRANSCRIPT_PATH replaces the stdin path.
#
# It never fails the agent: every problem exits 0 (silently, a Stop hook's output is noise).
# The copy is overwritten on each Stop, so the file always holds the whole transcript so far.

set -u

stdin_json=""
if [ ! -t 0 ]; then
  stdin_json="$(cat 2>/dev/null || true)"
fi

src="${RECUT_TRANSCRIPT_PATH:-}"
if [ -z "$src" ] && [ -n "$stdin_json" ]; then
  if command -v python3 >/dev/null 2>&1; then
    src="$(printf '%s' "$stdin_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("transcript_path",""))' 2>/dev/null || true)"
  else
    src="$(printf '%s' "$stdin_json" | sed -n 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
  fi
fi
[ -n "$src" ] && [ -f "$src" ] || exit 0

dest="${RECUT_SESSION:-}"
if [ -z "$dest" ]; then
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  root="${RECUT_TICKETS_DIR:-${RECUT_HOME:-$here/../..}/.appdata/tickets}"
  [ -f "$root/.current_session" ] && dest="$(head -n1 "$root/.current_session")"
fi
[ -n "$dest" ] && [ -d "$dest" ] || exit 0

cp -f "$src" "$dest/transcript.jsonl.tmp" 2>/dev/null && mv -f "$dest/transcript.jsonl.tmp" "$dest/transcript.jsonl" 2>/dev/null
exit 0
