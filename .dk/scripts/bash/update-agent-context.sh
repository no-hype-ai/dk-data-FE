#!/usr/bin/env bash
set -euo pipefail

# update-agent-context.sh — Regenerate AI agent context files from .dk/ state
#
# Usage: update-agent-context.sh [agent]
#
# Reads global memory (tags, stack, decisions, constitution) and spec memory
# (context.md for current feature) to compose agent context files.

DK_DIR=".dk"
CONFIG_FILE="$DK_DIR/config.yaml"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Error: $CONFIG_FILE not found. Run 'dkify init' first." >&2
  exit 1
fi

# Parse config
PROJECT_NAME=$(grep '^name:' "$CONFIG_FILE" | sed 's/^name: *//' | tr -d '"' | tr -d "'")
AI_AGENTS=$(grep '^ai:' "$CONFIG_FILE" | sed 's/^ai: *//')

# ─── Read Global Memory ──────────────────────────────────────────────

# Read active tags (extract just the Active Tags table, compact)
ACTIVE_TAGS=""
if [[ -f "$DK_DIR/memory/tags.md" ]]; then
  # Extract lines between "## Active Tags" and the next "##" heading
  ACTIVE_TAGS=$(awk '/^## Active Tags/{found=1; next} /^## /{if(found) exit} found' "$DK_DIR/memory/tags.md" | grep -v '^$' | head -20)
fi

# Read tech stack
STACK=""
if [[ -f "$DK_DIR/memory/stack.md" ]]; then
  STACK=$(cat "$DK_DIR/memory/stack.md")
fi

# Read decisions (compact: last 10 decisions)
DECISIONS=""
if [[ -f "$DK_DIR/memory/decisions.md" ]]; then
  DECISIONS=$(head -50 "$DK_DIR/memory/decisions.md")
fi

# Read constitution
CONSTITUTION=""
if [[ -f "$DK_DIR/memory/constitution.md" ]]; then
  CONSTITUTION=$(cat "$DK_DIR/memory/constitution.md")
fi

# ─── Read Spec Memory (current feature) ──────────────────────────────

CURRENT_FEATURE=""
SPEC_CONTEXT=""
SPECS_DIR="$DK_DIR/specs"

BRANCH=$(git branch --show-current 2>/dev/null || echo "")

# Find current feature directory
FEATURE_DIR=""
if [[ "$BRANCH" == feature/* ]]; then
  FEATURE_NAME="${BRANCH#feature/}"
  if [[ -d "$SPECS_DIR/$FEATURE_NAME" ]]; then
    FEATURE_DIR="$SPECS_DIR/$FEATURE_NAME"
  fi
fi

# Fallback: most recent spec directory
if [[ -z "$FEATURE_DIR" ]] && [[ -d "$SPECS_DIR" ]]; then
  LATEST=$(ls -td "$SPECS_DIR"/*/ 2>/dev/null | head -1)
  if [[ -n "${LATEST:-}" ]]; then
    FEATURE_DIR="${LATEST%/}"
  fi
fi

if [[ -n "$FEATURE_DIR" ]]; then
  FEATURE_NAME=$(basename "$FEATURE_DIR")
  CURRENT_FEATURE="Current feature: $FEATURE_NAME"

  # Build status indicators
  for artifact in spec.md plan.md tasks.md; do
    if [[ -f "$FEATURE_DIR/$artifact" ]]; then
      CURRENT_FEATURE="$CURRENT_FEATURE ($artifact)"
    fi
  done

  # Read spec-scoped context.md if it exists
  if [[ -f "$FEATURE_DIR/memory/context.md" ]]; then
    SPEC_CONTEXT=$(cat "$FEATURE_DIR/memory/context.md")
  fi
fi

# ─── Generate Context ────────────────────────────────────────────────

generate_context() {
  local agent="$1"
  cat << CTXEOF
# $PROJECT_NAME

This project uses [dk](https://github.com/tumeke-stealth/tumeke-tools) for spec-driven development.

## DK Commands

- \`/dk.constitution\` — Project conventions
- \`/dk.specify\` — Feature specification
- \`/dk.clarify\` — Resolve ambiguities
- \`/dk.plan\` — Implementation plan
- \`/dk.tasks\` — Task breakdown
- \`/dk.implement\` — Execute tasks
- \`/dk.analyze\` — Consistency audit
- \`/dk.checklist\` — Pre-merge checklist
- \`/dk.taskstoissues\` — Tasks to GitHub issues
- \`/dk.auto\` — Autonomous pipeline
- \`/dk.debug\` — E2E audit
- \`/dk.swarm\` — Parallel implementation
- \`/dk.tag\` — Manage principle tags
CTXEOF

  # Active tags (compact, always included)
  if [[ -n "$ACTIVE_TAGS" ]]; then
    echo ""
    echo "## Active Principle Tags"
    echo ""
    echo "$ACTIVE_TAGS"
  fi

  # Tech stack (compact, always included)
  if [[ -n "$STACK" ]] && [[ $(wc -l <<< "$STACK") -gt 5 ]]; then
    echo ""
    echo "$STACK"
  fi

  # Decisions (compact, always included)
  if [[ -n "$DECISIONS" ]] && [[ $(wc -l <<< "$DECISIONS") -gt 3 ]]; then
    echo ""
    echo "$DECISIONS"
  fi

  # Constitution (always included)
  if [[ -n "$CONSTITUTION" ]]; then
    echo ""
    echo "## Constitution"
    echo ""
    echo "$CONSTITUTION"
  fi

  # Current feature state
  if [[ -n "$CURRENT_FEATURE" ]]; then
    echo ""
    echo "## Project State"
    echo ""
    echo "$CURRENT_FEATURE"
  fi

  # Spec-scoped context (only when on a feature branch)
  if [[ -n "$SPEC_CONTEXT" ]]; then
    echo ""
    echo "## Feature Context"
    echo ""
    echo "$SPEC_CONTEXT"
  fi
}

# ─── Write Context Files ─────────────────────────────────────────────

update_agent() {
  local agent="$1"
  local context_file=""

  case "$agent" in
    claude) context_file="CLAUDE.md" ;;
    codex) context_file="AGENTS.md" ;;
    gemini) context_file="GEMINI.md" ;;
    qwen) context_file="QWEN.md" ;;
    *)
      echo "Warning: Unknown agent '$agent', skipping." >&2
      return
      ;;
  esac

  generate_context "$agent" > "$context_file"
  echo "Updated $context_file"
}

if [[ $# -gt 0 ]]; then
  update_agent "$1"
else
  echo "$AI_AGENTS" | tr -d '[]' | tr ',' '\n' | while read -r agent; do
    agent=$(echo "$agent" | tr -d ' "' | tr -d "'")
    if [[ -n "$agent" ]]; then
      update_agent "$agent"
    fi
  done
fi
