#!/usr/bin/env bash
# mesh-status-brief.sh — terse mesh digest for the Claude SessionStart hook.
#
# Safe to run in any dkified project. Exits 0 silently when the mesh is off
# or missing; otherwise prints a short digest (peer status + handoffs
# involving this project).

set -u

# Fast path: if dkify isn't on PATH, do nothing. Don't fail the session.
if ! command -v dkify >/dev/null 2>&1; then
  exit 0
fi

# Fast path: if .dk/config.yaml is missing or mesh is off, do nothing.
CONFIG=".dk/config.yaml"
if [[ ! -f "$CONFIG" ]]; then
  exit 0
fi

# Crude grep-based mode check. Avoids a Python startup cost.
MODE="$(grep -E '^\s+mode:' "$CONFIG" 2>/dev/null | head -n1 | awk '{print $2}' | tr -d '"')"
if [[ -z "$MODE" || "$MODE" == "off" ]]; then
  exit 0
fi

# Defer to the Typer CLI for the actual digest.
# --brief keeps output short; CLI already no-ops if mesh dir missing.
dkify mesh status --brief 2>/dev/null || true
