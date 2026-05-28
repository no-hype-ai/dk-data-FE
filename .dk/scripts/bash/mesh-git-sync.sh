#!/usr/bin/env bash
# mesh-git-sync.sh — wrapper around `dkify mesh sync` for cron / git hooks.
#
# Pulls + pushes the mesh coordinator repo. No-op for mesh.mode = off/on-local.
# Surfaces conflicts rather than auto-resolving.

set -euo pipefail

if ! command -v dkify >/dev/null 2>&1; then
  echo "mesh-git-sync: dkify not on PATH; nothing to do." >&2
  exit 0
fi

dkify mesh sync
