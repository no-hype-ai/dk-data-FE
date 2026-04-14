#!/usr/bin/env bash
# verify-feature-dir.sh — resolve FEATURE_DIR for the current feature
# branch and validate that tasks.md exists.
#
# Wraps `.dk/scripts/bash/check-prerequisites.sh --json --require-tasks
# --include-tasks` so dk.stage modes can reuse the exact same prereq
# logic that dk.implement and dk.swarm already rely on.
#
# Output: JSON on stdout with keys {feature_dir, branch, tasks_present,
# stage_status_present}. Non-zero exit if prerequisites fail.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
if [[ -z "$REPO_ROOT" ]]; then
  echo '{"error":"not in a git repo"}' >&2
  exit 2
fi

CHECK="${REPO_ROOT}/.dk/scripts/bash/check-prerequisites.sh"
if [[ ! -x "$CHECK" ]]; then
  echo "{\"error\":\"check-prerequisites.sh not found at ${CHECK}\"}" >&2
  exit 3
fi

PREREQ_JSON="$("$CHECK" --json --require-tasks --include-tasks 2>&1)" || {
  echo "$PREREQ_JSON" >&2
  exit 4
}

FEATURE_DIR="$(echo "$PREREQ_JSON" | grep -o '"FEATURE_DIR":"[^"]*"' | sed 's/.*"FEATURE_DIR":"\([^"]*\)".*/\1/')"
BRANCH="$(echo "$PREREQ_JSON" | grep -o '"BRANCH":"[^"]*"' | sed 's/.*"BRANCH":"\([^"]*\)".*/\1/')"

if [[ -z "$FEATURE_DIR" ]]; then
  echo '{"error":"could not parse FEATURE_DIR from check-prerequisites.sh output"}' >&2
  echo "$PREREQ_JSON" >&2
  exit 5
fi

TASKS_PRESENT=false
STAGE_STATUS_PRESENT=false
[[ -f "${FEATURE_DIR}/tasks.md" ]] && TASKS_PRESENT=true
[[ -f "${FEATURE_DIR}/stage-status.md" ]] && STAGE_STATUS_PRESENT=true

printf '{"feature_dir":"%s","branch":"%s","tasks_present":%s,"stage_status_present":%s}\n' \
  "$FEATURE_DIR" "$BRANCH" "$TASKS_PRESENT" "$STAGE_STATUS_PRESENT"
