#!/usr/bin/env bash
# mesh-loop-prefilter.sh — cheap "is there work?" check for the mesh-loop watcher.
#
# Runs on every cron tick. Most ticks exit cleanly with HAS_WORK=0 and produce
# no output. When inbox or peer statuses have changed since the last marker,
# emits HAS_WORK=1 plus a human-readable diff summary so a sub-agent can be
# invoked with focused context.
#
# Exit codes:
#   0  — ran cleanly (check HAS_WORK in the output)
#   2  — usage error
#   3  — mesh CLI not available
#
# Output (key=value lines, machine-parseable):
#   HAS_WORK=0|1
#   DIFF_SUMMARY=<one-line description, empty if HAS_WORK=0>
#   CHANGED_HANDOFFS=<comma-separated basenames, empty if HAS_WORK=0>
#   NEW_HANDOFFS=<comma-separated basenames, empty if HAS_WORK=0>
#   CLOSED_HANDOFFS=<comma-separated basenames, empty if HAS_WORK=0>
#
# The caller (the /loop skill body) reads these and decides whether to spawn
# an Agent sub-task.
set -euo pipefail

PROJECT="${1:-dk-data-FE}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKER="${SCRIPT_DIR}/mesh-loop-marker.sh"
MESH_ROOT="${DK_MESH_DIR:-$HOME/.dk-mesh}"
TAG="${DK_MESH_TAG:-dk}"

# Hard prerequisites.
if ! command -v dkify >/dev/null 2>&1; then
  echo "HAS_WORK=0"
  echo "DIFF_SUMMARY=dkify CLI not available; skipping"
  exit 3
fi
if [[ ! -d "$MESH_ROOT" ]]; then
  echo "HAS_WORK=0"
  echo "DIFF_SUMMARY=mesh dir $MESH_ROOT not present; skipping"
  exit 0
fi

# Snapshot the inbox BEFORE sync so we can compute what arrived/closed.
prev_open=$(ls "${MESH_ROOT}/handoffs/${TAG}/open" 2>/dev/null | LC_ALL=C sort || true)

# Pull remote state. Silent on success; errors go to stderr.
dkify mesh sync >/dev/null 2>&1 || true

# Snapshot AFTER sync.
curr_open=$(ls "${MESH_ROOT}/handoffs/${TAG}/open" 2>/dev/null | LC_ALL=C sort || true)

# Compute the marker hash AFTER sync (this is what we'll persist if we trigger).
curr_hash="$(bash "$MARKER" hash "$PROJECT")"
prev_hash="$(bash "$MARKER" read "$PROJECT")"

# Decide.
if [[ "$curr_hash" == "$prev_hash" ]]; then
  echo "HAS_WORK=0"
  echo "DIFF_SUMMARY="
  exit 0
fi

# State changed. Categorize.
new_handoffs=$(LC_ALL=C comm -13 <(echo "$prev_open") <(echo "$curr_open") | tr '\n' ',' | sed 's/,$//')
closed_handoffs=$(LC_ALL=C comm -23 <(echo "$prev_open") <(echo "$curr_open") | tr '\n' ',' | sed 's/,$//')
# Edited handoffs = present in both, but with newer mtime than the prev marker run.
# Heuristic: if marker file exists, anything modified after the marker file's
# mtime is "changed". If no marker yet, treat as "all current = changed".
marker_file="${MESH_ROOT}/.markers/${PROJECT}.sha"
if [[ -f "$marker_file" ]]; then
  if stat -f '%m' "$marker_file" >/dev/null 2>&1; then
    marker_mtime=$(stat -f '%m' "$marker_file")
  else
    marker_mtime=$(stat -c '%Y' "$marker_file")
  fi
  changed_handoffs=$(
    LC_ALL=C comm -12 <(echo "$prev_open") <(echo "$curr_open") \
      | while read -r name; do
          [[ -z "$name" ]] && continue
          f="${MESH_ROOT}/handoffs/${TAG}/open/$name"
          if stat -f '%m' "$f" >/dev/null 2>&1; then
            mt=$(stat -f '%m' "$f")
          else
            mt=$(stat -c '%Y' "$f")
          fi
          [[ "$mt" -gt "$marker_mtime" ]] && echo "$name"
        done | tr '\n' ',' | sed 's/,$//'
  )
else
  changed_handoffs=""
fi

# Build summary.
summary_parts=()
[[ -n "$new_handoffs" ]] && summary_parts+=("$(echo "$new_handoffs" | tr ',' '\n' | wc -l | tr -d ' ') new")
[[ -n "$closed_handoffs" ]] && summary_parts+=("$(echo "$closed_handoffs" | tr ',' '\n' | wc -l | tr -d ' ') closed")
[[ -n "$changed_handoffs" ]] && summary_parts+=("$(echo "$changed_handoffs" | tr ',' '\n' | wc -l | tr -d ' ') changed")
if [[ ${#summary_parts[@]} -eq 0 ]]; then
  # Hash differs but file-set + mtimes don't categorize — likely a peer status republish.
  summary_parts+=("peer status republish")
fi
IFS=, summary="${summary_parts[*]}"

echo "HAS_WORK=1"
echo "DIFF_SUMMARY=$summary"
echo "NEW_HANDOFFS=$new_handoffs"
echo "CLOSED_HANDOFFS=$closed_handoffs"
echo "CHANGED_HANDOFFS=$changed_handoffs"
echo "CURR_HASH=$curr_hash"
