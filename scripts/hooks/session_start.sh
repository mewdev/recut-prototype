#!/usr/bin/env bash
# Claude Code SessionStart hook: tell Claude (and so the operator) which shipped cuts still
# have no client feedback logged. Whatever this prints is added to Claude's context;
# AGENTS.md tells Claude to pass the reminder on in its first reply. Prints nothing when
# there's nothing to remind about, and never fails the session.
if command -v recut >/dev/null 2>&1; then
  recut ticket awaiting --quiet 2>/dev/null || true
fi
exit 0
