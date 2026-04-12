#!/usr/bin/env bash
# common.sh — Shared utilities for dk scripts
#
# Source this file from other scripts:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/common.sh"

set -euo pipefail

# ─── Repository Management ────────────────────────────────────────────

# Find the .dk/ root directory by walking up from the current directory
find_dk_root() {
  local dir="$PWD"
  while [[ "$dir" != "/" ]]; do
    if [[ -d "$dir/.dk" ]]; then
      echo "$dir/.dk"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  echo "Error: .dk/ directory not found. Run 'dkify init' first." >&2
  return 1
}

# Find the repository root (parent of .dk/)
get_repo_root() {
  local dk_root
  dk_root="$(find_dk_root)"
  dirname "$dk_root"
}

# Check if we're in a git repository
has_git() {
  git rev-parse --is-inside-work-tree &>/dev/null
}

# ─── Branch Handling ──────────────────────────────────────────────────

# Get the current git branch name
get_current_branch() {
  git branch --show-current 2>/dev/null || echo ""
}

# Check if we're on a feature branch (feature/*)
check_feature_branch() {
  local branch
  branch="$(get_current_branch)"
  if [[ "$branch" == feature/* ]]; then
    return 0
  fi
  return 1
}

# Extract feature name from branch (feature/001-name → 001-name)
get_feature_name() {
  local branch
  branch="$(get_current_branch)"
  echo "${branch#feature/}"
}

# Find the feature directory for the current branch
get_feature_dir() {
  local dk_root repo_root feature_name feature_dir

  dk_root="$(find_dk_root)"
  repo_root="$(dirname "$dk_root")"

  if check_feature_branch; then
    feature_name="$(get_feature_name)"
    feature_dir="$dk_root/specs/$feature_name"
    if [[ -d "$feature_dir" ]]; then
      echo "$feature_dir"
      return 0
    fi
  fi

  # Fallback: most recent spec directory
  local latest
  latest="$(ls -td "$dk_root/specs"/*/ 2>/dev/null | head -1)"
  if [[ -n "${latest:-}" ]]; then
    echo "${latest%/}"
    return 0
  fi

  echo "Error: No feature directory found in $dk_root/specs/" >&2
  return 1
}

# Get all important paths for the current feature
get_feature_paths() {
  local feature_dir spec_file plan_file tasks_file

  feature_dir="$(get_feature_dir)"
  spec_file="$feature_dir/spec.md"
  plan_file="$feature_dir/plan.md"
  tasks_file="$feature_dir/tasks.md"

  echo "FEATURE_DIR=$feature_dir"
  echo "SPEC_FILE=$spec_file"
  echo "PLAN_FILE=$plan_file"
  echo "TASKS_FILE=$tasks_file"
}

# ─── Data Encoding ────────────────────────────────────────────────────

# Escape a string for JSON output
json_escape() {
  local str="$1"
  str="${str//\\/\\\\}"
  str="${str//\"/\\\"}"
  str="${str//$'\n'/\\n}"
  str="${str//$'\t'/\\t}"
  str="${str//$'\r'/\\r}"
  echo "$str"
}

# Check if jq is available
has_jq() {
  command -v jq &>/dev/null
}

# ─── Validation ───────────────────────────────────────────────────────

# Check that a file exists, with a helpful error message
check_file() {
  local path="$1"
  local description="${2:-file}"
  if [[ ! -f "$path" ]]; then
    echo "Error: $description not found at $path" >&2
    return 1
  fi
}

# Check that a directory exists
check_dir() {
  local path="$1"
  local description="${2:-directory}"
  if [[ ! -d "$path" ]]; then
    echo "Error: $description not found at $path" >&2
    return 1
  fi
}

# ─── Template Resolution ─────────────────────────────────────────────

# Resolve a template file with priority: overrides → presets → extensions → core
# Usage: resolve_template "spec-template.md"
resolve_template() {
  local template_name="$1"
  local dk_root

  dk_root="$(find_dk_root)"

  # 1. User overrides
  local override="$dk_root/templates/overrides/$template_name"
  if [[ -f "$override" ]]; then
    echo "$override"
    return 0
  fi

  # 2. Core templates
  local core="$dk_root/templates/$template_name"
  if [[ -f "$core" ]]; then
    echo "$core"
    return 0
  fi

  echo "Error: Template '$template_name' not found" >&2
  return 1
}

# ─── Config Reading ──────────────────────────────────────────────────

# Read a simple key from config.yaml (basic grep-based, no yq dependency)
read_config() {
  local key="$1"
  local dk_root config_file

  dk_root="$(find_dk_root)"
  config_file="$dk_root/config.yaml"

  if [[ ! -f "$config_file" ]]; then
    echo "Error: $config_file not found" >&2
    return 1
  fi

  grep "^${key}:" "$config_file" | sed "s/^${key}: *//" | tr -d '"' | tr -d "'"
}
