#!/usr/bin/env bash
set -euo pipefail

# check-prerequisites.sh — Validate DK project state and return paths
#
# Usage: check-prerequisites.sh [--json] [--paths-only] [--require-tasks] [--include-tasks]
#
# Checks:
#   - .dk/ directory exists
#   - Current branch is a feature branch
#   - Spec file exists
#   - Plan file exists (unless --paths-only)
#   - Tasks file exists (if --require-tasks)

DK_DIR=".dk"
SPECS_DIR="$DK_DIR/specs"

JSON_OUTPUT=false
PATHS_ONLY=false
REQUIRE_TASKS=false
INCLUDE_TASKS=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --json) JSON_OUTPUT=true; shift ;;
    --paths-only) PATHS_ONLY=true; shift ;;
    --require-tasks) REQUIRE_TASKS=true; shift ;;
    --include-tasks) INCLUDE_TASKS=true; shift ;;
    *) shift ;;
  esac
done

# Check .dk/ exists
if [[ ! -d "$DK_DIR" ]]; then
  echo "Error: .dk/ directory not found. Run 'dkify init' first." >&2
  exit 1
fi

# Find current feature directory (most recent spec dir)
BRANCH=$(git branch --show-current 2>/dev/null || echo "")
FEATURE_DIR=""
FEATURE_SPEC=""
IMPL_PLAN=""
TASKS_FILE=""
AVAILABLE_DOCS=()

if [[ "$BRANCH" == feature/* ]]; then
  FEATURE_NAME="${BRANCH#feature/}"
  if [[ -d "$SPECS_DIR/$FEATURE_NAME" ]]; then
    FEATURE_DIR="$(pwd)/$SPECS_DIR/$FEATURE_NAME"
  fi
fi

# Fallback: find the most recent spec directory
if [[ -z "$FEATURE_DIR" ]] && [[ -d "$SPECS_DIR" ]]; then
  LATEST=$(ls -td "$SPECS_DIR"/*/ 2>/dev/null | head -1)
  if [[ -n "$LATEST" ]]; then
    FEATURE_DIR="$(pwd)/${LATEST%/}"
  fi
fi

if [[ -z "$FEATURE_DIR" ]]; then
  echo "Error: No feature directory found in $SPECS_DIR/" >&2
  exit 1
fi

# Check for spec file
if [[ -f "$FEATURE_DIR/spec.md" ]]; then
  FEATURE_SPEC="$FEATURE_DIR/spec.md"
  AVAILABLE_DOCS+=("spec.md")
fi

# Check for plan
if [[ -f "$FEATURE_DIR/plan.md" ]]; then
  IMPL_PLAN="$FEATURE_DIR/plan.md"
  AVAILABLE_DOCS+=("plan.md")
fi

# Check for tasks
if [[ -f "$FEATURE_DIR/tasks.md" ]]; then
  TASKS_FILE="$FEATURE_DIR/tasks.md"
  AVAILABLE_DOCS+=("tasks.md")
fi

# Check for optional artifacts
for artifact in research.md data-model.md quickstart.md; do
  if [[ -f "$FEATURE_DIR/$artifact" ]]; then
    AVAILABLE_DOCS+=("$artifact")
  fi
done

if [[ -d "$FEATURE_DIR/contracts" ]]; then
  AVAILABLE_DOCS+=("contracts/")
fi

# Validate requirements
if [[ "$REQUIRE_TASKS" == true ]] && [[ -z "$TASKS_FILE" ]]; then
  echo "Error: tasks.md not found in $FEATURE_DIR. Run /dk.tasks first." >&2
  exit 1
fi

if [[ "$JSON_OUTPUT" == true ]]; then
  DOCS_JSON=$(printf '"%s",' "${AVAILABLE_DOCS[@]}" | sed 's/,$//')
  cat << EOF
{
  "FEATURE_DIR": "$FEATURE_DIR",
  "FEATURE_SPEC": "$FEATURE_SPEC",
  "IMPL_PLAN": "$IMPL_PLAN",
  "TASKS_FILE": "$TASKS_FILE",
  "SPECS_DIR": "$(pwd)/$SPECS_DIR",
  "BRANCH": "$BRANCH",
  "AVAILABLE_DOCS": [$DOCS_JSON]
}
EOF
else
  echo "Feature dir: $FEATURE_DIR"
  echo "Spec:        $FEATURE_SPEC"
  echo "Plan:        $IMPL_PLAN"
  echo "Tasks:       $TASKS_FILE"
  echo "Docs:        ${AVAILABLE_DOCS[*]}"
fi
