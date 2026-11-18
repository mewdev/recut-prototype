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
  repo_dir="${RECUT_HOME:-$here/../..}"
  if [ -n "${RECUT_TICKETS_DIR:-}" ]; then root="$RECUT_TICKETS_DIR"
  elif [ -d "$repo_dir/../recut-data/.git" ]; then root="$repo_dir/../recut-data/tickets"
  else root="$repo_dir/.appdata/tickets"; fi
  [ -f "$root/.current_session" ] && dest="$(head -n1 "$root/.current_session")"
fi
[ -n "$dest" ] && [ -d "$dest" ] || exit 0

cp -f "$src" "$dest/transcript.jsonl.tmp" 2>/dev/null && mv -f "$dest/transcript.jsonl.tmp" "$dest/transcript.jsonl" 2>/dev/null
# save to the data repo (recut-data) in the background; never blocks or fails the agent
if [ "${RECUT_AUTOSYNC:-1}" != "0" ] && command -v recut >/dev/null 2>&1; then
  # sync exactly the tickets folder that holds this session (<tickets>/<ticket>/sessions/<n>)
  tickets_root="$(cd "$dest/../../.." 2>/dev/null && pwd)"
  [ -n "$tickets_root" ] && (RECUT_TICKETS_DIR="$tickets_root" recut sync --quiet \
    -m "sync: transcript $(basename "$(dirname "$(dirname "$dest")")")/s$(basename "$dest")" >/dev/null 2>&1 &)
fi

# Review reminder: the latest iteration is rendered but has no review. Block the stop ONCE per
# iteration (marker in $TMPDIR, not the data repo) so the agent asks the operator for a verdict
# and records it with `recut ticket review`. The agent must never pick the verdict itself.
case "$stdin_json" in *'"stop_hook_active": true'*|*'"stop_hook_active":true'*) exit 0 ;; esac
k="$(ls "$dest/iterations" 2>/dev/null | grep -E '^[0-9]+$' | sort -n | tail -n1)"
it="$dest/iterations/$k"
[ -n "$k" ] && [ -f "$it/render.json" ] && [ ! -f "$it/review.json" ] || exit 0
n="$(basename "$dest")"; tid="$(basename "$(dirname "$(dirname "$dest")")")"
marker="${TMPDIR:-/tmp}/recut-review-asked-$tid-s$n-it$k"
[ -f "$marker" ] && exit 0
touch "$marker" 2>/dev/null || exit 0
printf '{"decision": "block", "reason": "Ticket %s s%s it%s is rendered but has no review. If the operator already gave a verdict in this session, record it with `recut ticket review %s --verdict ship|fixable|reject --ok all|s1,... --bad sN:tag+tag --note \\"<their words + session facts>\\"`. Otherwise ask them for their verdict (and any bad splices) and stop. Never choose the verdict yourself."}\n' \
  "$tid" "$n" "$k" "$tid"
exit 0
