#!/usr/bin/env bash
# distributor-status-brief.sh — terse distributor digest for SessionStart.
#
# Safe to run in any dkified project. Exits 0 silently when the distributor is
# off or missing; otherwise prints a short digest (budget remaining, last 3
# runs, top alias per kind from the leaderboard).

set -u

# Fast path: if dkify isn't on PATH, do nothing.
if ! command -v dkify >/dev/null 2>&1; then
  exit 0
fi

# Fast path: if config is missing, do nothing.
CONFIG=".dk/config.yaml"
if [[ ! -f "$CONFIG" ]]; then
  exit 0
fi

# Look for `distributor:` block — the next non-empty indented `mode:` line is
# its mode. Avoid a full Python startup if distributor isn't present at all.
if ! grep -q '^distributor:' "$CONFIG" 2>/dev/null; then
  exit 0
fi

# Pull the distributor.mode by scanning lines after `distributor:`.
MODE="$(awk '
  /^distributor:/ { in_block=1; next }
  in_block && /^[a-zA-Z]/ { in_block=0 }
  in_block && /^[[:space:]]+mode:/ { sub(/^[[:space:]]+mode:[[:space:]]*/, ""); gsub(/"/, ""); print; exit }
' "$CONFIG")"

if [[ -z "$MODE" || "$MODE" == "off" ]]; then
  exit 0
fi

# Defer to the Typer CLI for the actual digest.
dkify distributor status --brief 2>/dev/null || true
