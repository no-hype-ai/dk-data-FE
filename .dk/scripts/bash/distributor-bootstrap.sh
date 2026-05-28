#!/usr/bin/env bash
# distributor-bootstrap.sh — first-run helper for the vendored dkd package.
#
# Creates .dk/distributor/.venv and installs the package in editable mode.
# Idempotent: skips work if the venv is already present and up to date.
#
# Usage:
#   bash .dk/scripts/bash/distributor-bootstrap.sh
#   bash .dk/scripts/bash/distributor-bootstrap.sh --force   # rebuild venv

set -euo pipefail

DIST_DIR=".dk/distributor"
VENV_DIR="$DIST_DIR/.venv"
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
  esac
done

if [[ ! -d "$DIST_DIR" ]]; then
  echo "error: $DIST_DIR not found. Run 'dkify upgrade --distributor' first." >&2
  exit 1
fi

if [[ ! -f "$DIST_DIR/pyproject.toml" ]]; then
  echo "error: $DIST_DIR/pyproject.toml missing — distributor scaffold incomplete." >&2
  exit 1
fi

if [[ "$FORCE" == "1" && -d "$VENV_DIR" ]]; then
  echo "Removing existing venv (--force) ..."
  rm -rf "$VENV_DIR"
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating venv at $VENV_DIR ..."
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Installing dkd in editable mode ..."
pip install --quiet --upgrade pip
pip install --quiet -e "$DIST_DIR[dev]" 2>/dev/null || pip install --quiet -e "$DIST_DIR"

echo "OK. Verify with: source $VENV_DIR/bin/activate && dkd --help"
