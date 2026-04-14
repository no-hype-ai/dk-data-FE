#!/usr/bin/env bash
# prestaged_smoke.sh — minimal smoke test for the 005-prestaged-hydration
# feature. Runs the hydrator in --dry-run for one tier against a local
# Postgres so CI / developers can confirm the module imports, the load
# plan constructs, and the artifact walker finds something.
#
# Usage:
#   scripts/prestaged_smoke.sh [tier_num]
#
# Defaults:
#   PRESTAGED_ROOT=./data
#   PG_URL=postgresql://postgres:postgres@localhost:5432/dk_data_test
#   tier_num=1  (metadata + lineage — smallest tier)
#
# Exit 0 on success, non-zero on module import or plan failure.
# Intentionally short — this is a smoke, not a full integration test.

set -euo pipefail

TIER="${1:-1}"
export PRESTAGED_ROOT="${PRESTAGED_ROOT:-$PWD/data}"
export PG_URL="${PG_URL:-postgresql://postgres:postgres@localhost:5432/dk_data_test}"

if [[ ! -d "$PRESTAGED_ROOT" ]]; then
  echo "ERROR: PRESTAGED_ROOT does not exist: $PRESTAGED_ROOT" >&2
  exit 1
fi

echo ">> prestaged smoke: tier=$TIER root=$PRESTAGED_ROOT"

python -m dk_data.ingestion.prestaged \
  --dry-run \
  --only-tier "$TIER" \
  --source-list all

echo ">> prestaged smoke: ok"
