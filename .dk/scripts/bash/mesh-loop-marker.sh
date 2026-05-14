#!/usr/bin/env bash
# mesh-loop-marker.sh — read/write the per-project mesh-loop watcher marker.
#
# Usage:
#   mesh-loop-marker.sh hash <project>     # print current sha of inbox+statuses
#   mesh-loop-marker.sh read <project>     # print stored marker (empty if none)
#   mesh-loop-marker.sh write <project> <sha>   # persist marker
#
# The marker captures a sha256 over:
#   - filenames + mtimes of ~/.dk-mesh/handoffs/<tag>/open/*.md
#   - filenames + mtimes of ~/.dk-mesh/projects/<tag>/*.md
# This catches new handoffs, deleted/closed handoffs, status republishes,
# and edits to any open handoff (e.g. peer responses).
#
# Project arg is the dk-data-FE-style project name (matches mesh.yaml entry).
set -euo pipefail

MESH_ROOT="${DK_MESH_DIR:-$HOME/.dk-mesh}"
MARKER_DIR="${MESH_ROOT}/.markers"
TAG="${DK_MESH_TAG:-dk}"

mode="${1:-}"
project="${2:-}"
if [[ -z "$mode" || -z "$project" ]]; then
  echo "Usage: $0 {hash|read|write} <project> [sha]" >&2
  exit 2
fi

case "$mode" in
  hash)
    # Compose listing: handoffs + statuses, name+mtime, sorted for determinism.
    {
      find "${MESH_ROOT}/handoffs/${TAG}/open" -name '*.md' -type f 2>/dev/null \
        | while read -r f; do
            stat -f '%N %m' "$f" 2>/dev/null || stat -c '%n %Y' "$f" 2>/dev/null
          done
      find "${MESH_ROOT}/projects/${TAG}" -name '*.md' -type f 2>/dev/null \
        | while read -r f; do
            stat -f '%N %m' "$f" 2>/dev/null || stat -c '%n %Y' "$f" 2>/dev/null
          done
    } | LC_ALL=C sort | shasum -a 256 | awk '{print $1}'
    ;;
  read)
    marker_file="${MARKER_DIR}/${project}.sha"
    [[ -f "$marker_file" ]] && cat "$marker_file" || true
    ;;
  write)
    sha="${3:-}"
    if [[ -z "$sha" ]]; then
      echo "Usage: $0 write <project> <sha>" >&2
      exit 2
    fi
    mkdir -p "$MARKER_DIR"
    echo "$sha" > "${MARKER_DIR}/${project}.sha"
    ;;
  *)
    echo "Unknown mode: $mode (expected hash|read|write)" >&2
    exit 2
    ;;
esac
