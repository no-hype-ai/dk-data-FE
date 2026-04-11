#!/usr/bin/env bash
set -euo pipefail

# setup-plan.sh — Prepare the plan.md scaffold and return paths
#
# Usage: setup-plan.sh [--json]

DK_DIR=".dk"
SPECS_DIR="$DK_DIR/specs"
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --json) JSON_OUTPUT=true; shift ;;
    *) shift ;;
  esac
done

# Find current feature directory
BRANCH=$(git branch --show-current 2>/dev/null || echo "")
FEATURE_DIR=""

if [[ "$BRANCH" == feature/* ]]; then
  FEATURE_NAME="${BRANCH#feature/}"
  if [[ -d "$SPECS_DIR/$FEATURE_NAME" ]]; then
    FEATURE_DIR="$(pwd)/$SPECS_DIR/$FEATURE_NAME"
  fi
fi

if [[ -z "$FEATURE_DIR" ]] && [[ -d "$SPECS_DIR" ]]; then
  LATEST=$(ls -td "$SPECS_DIR"/*/ 2>/dev/null | head -1)
  if [[ -n "$LATEST" ]]; then
    FEATURE_DIR="$(pwd)/${LATEST%/}"
  fi
fi

if [[ -z "$FEATURE_DIR" ]]; then
  echo "Error: No feature directory found. Run /dk.specify first." >&2
  exit 1
fi

FEATURE_SPEC="$FEATURE_DIR/spec.md"
IMPL_PLAN="$FEATURE_DIR/plan.md"

if [[ ! -f "$FEATURE_SPEC" ]]; then
  echo "Error: spec.md not found in $FEATURE_DIR. Run /dk.specify first." >&2
  exit 1
fi

# Create contracts directory
mkdir -p "$FEATURE_DIR/contracts"

if [[ "$JSON_OUTPUT" == true ]]; then
  cat << EOF
{
  "FEATURE_SPEC": "$FEATURE_SPEC",
  "IMPL_PLAN": "$IMPL_PLAN",
  "SPECS_DIR": "$FEATURE_DIR",
  "BRANCH": "$BRANCH"
}
EOF
else
  echo "Spec:   $FEATURE_SPEC"
  echo "Plan:   $IMPL_PLAN"
  echo "Dir:    $FEATURE_DIR"
fi
