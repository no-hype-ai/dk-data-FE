#!/usr/bin/env bash
# check-pending-migrations.sh
# Compares SQL migration files against meta.schema_migrations to detect
# migrations that exist on disk but haven't been applied to the database.
#
# Usage:
#   ./scripts/check-pending-migrations.sh
#
# Env vars (same as run_migrations.py):
#   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
#   Or: DATABASE_URL
#
# Exit codes:
#   0 = all migrations applied
#   1 = pending migrations found (prints list)
#   2 = could not connect to database

set -euo pipefail

MIGRATIONS_DIR="${MIGRATIONS_DIR:-src/dk_data/sql/migrations}"

# ── Database connection ──────────────────────────────────────────────────────

if [ -n "${DATABASE_URL:-}" ]; then
  PSQL_CONN="$DATABASE_URL"
else
  PSQL_CONN="postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-dk_data}"
fi

# Test connection
if ! psql "$PSQL_CONN" -c "SELECT 1" > /dev/null 2>&1; then
  echo "ERROR: Cannot connect to database"
  exit 2
fi

# ── Get applied migrations ───────────────────────────────────────────────────

# Ensure meta.schema_migrations exists
TABLE_EXISTS=$(psql "$PSQL_CONN" -t -A -c \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='meta' AND table_name='schema_migrations';" 2>/dev/null || echo "0")

APPLIED_VERSIONS=""
if [ "$TABLE_EXISTS" = "1" ]; then
  APPLIED_VERSIONS=$(psql "$PSQL_CONN" -t -A -c \
    "SELECT version FROM meta.schema_migrations ORDER BY version;" 2>/dev/null || echo "")
fi

# ── Scan migration files ─────────────────────────────────────────────────────

PENDING=()
TOTAL=0

for f in "$MIGRATIONS_DIR"/*.sql; do
  [ -f "$f" ] || continue
  basename=$(basename "$f")

  # Skip README and non-numbered files
  [[ "$basename" =~ ^[0-9]+ ]] || continue

  # Extract version number (numeric prefix)
  version=$(echo "$basename" | grep -oE '^[0-9]+')
  TOTAL=$((TOTAL + 1))

  # Check if version is in applied list
  if echo "$APPLIED_VERSIONS" | grep -qx "$version"; then
    continue
  fi

  PENDING+=("$version  $basename")
done

# ── Report ───────────────────────────────────────────────────────────────────

APPLIED_COUNT=$(echo "$APPLIED_VERSIONS" | grep -c . 2>/dev/null || echo "0")

if [ ${#PENDING[@]} -eq 0 ]; then
  echo "All $TOTAL migrations applied ($APPLIED_COUNT tracked in meta.schema_migrations)"
  exit 0
fi

echo "PENDING MIGRATIONS: ${#PENDING[@]} of $TOTAL not yet applied"
echo ""
for p in "${PENDING[@]}"; do
  echo "  - $p"
done
echo ""
echo "Run: python -m dk_data.scripts.run_migrations"
exit 1
