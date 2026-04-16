#!/usr/bin/env bash
# read-stage-status.sh — extract a structured summary of the current
# stage-status.md without asking the model to parse markdown line by
# line. Output is JSON on stdout.
#
# Keys emitted:
#   feature_dir           — the FEATURE_DIR path (from arg 1, required)
#   pipeline_state        — init | in-progress | closing | done | unknown
#   current_stage         — the Stage N from the pointer line, or "" if unset
#   dashboard             — the raw dashboard line (emoji sequence)
#   next_action           — the single-line imperative from the "Next action" section
#   stage_status_exists   — "true" | "false"
#
# Usage: scripts/read-stage-status.sh /path/to/FEATURE_DIR
# Non-zero exit only on argument errors; missing file is signalled via
# stage_status_exists=false so the caller can decide what to do.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo '{"error":"usage: read-stage-status.sh FEATURE_DIR"}' >&2
  exit 2
fi

FEATURE_DIR="$1"
FILE="${FEATURE_DIR}/stage-status.md"

if [[ ! -f "$FILE" ]]; then
  printf '{"stage_status_exists":false,"feature_dir":"%s"}\n' "$FEATURE_DIR"
  exit 0
fi

# Pipeline state
PIPELINE_STATE="$(grep -m1 -E '^\*\*Pipeline state\*\*:' "$FILE" | sed 's/.*: *//; s/ *$//' || true)"
[[ -z "$PIPELINE_STATE" ]] && PIPELINE_STATE="unknown"

# Current stage pointer
CURRENT_STAGE="$(grep -m1 -E '^\*\*Current stage pointer\*\*:' "$FILE" | sed 's/.*: *//; s/ *$//' || true)"

# Dashboard — the first non-empty line after "## Dashboard"
DASHBOARD="$(awk '/^## Dashboard$/{flag=1; next} flag && NF{print; exit}' "$FILE" | sed 's/"/\\"/g')"

# Next action — the first non-empty line after "## Next action"
NEXT_ACTION="$(awk '/^## Next action$/{flag=1; next} flag && NF{print; exit}' "$FILE" | sed 's/"/\\"/g')"

# Escape quotes and newlines defensively for JSON
PIPELINE_STATE="${PIPELINE_STATE//\"/\\\"}"
CURRENT_STAGE="${CURRENT_STAGE//\"/\\\"}"

printf '{"stage_status_exists":true,"feature_dir":"%s","pipeline_state":"%s","current_stage":"%s","dashboard":"%s","next_action":"%s"}\n' \
  "$FEATURE_DIR" "$PIPELINE_STATE" "$CURRENT_STAGE" "$DASHBOARD" "$NEXT_ACTION"
