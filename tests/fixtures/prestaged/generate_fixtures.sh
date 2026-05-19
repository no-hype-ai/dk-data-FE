#!/usr/bin/env bash
# generate_fixtures.sh — produce PGDMP `.dump` fixtures for
# tests/load/test_prestaged_e2e.py and tests/ingestion/test_prestaged_*.
#
# Generates four on-disk layouts that exercise the discovery walker:
#
#   _staging/archive-001/dk-data-files/mol_raw/chembl_sample/
#       1_chembl_sample.dump
#       retry_chembl_sample.dump
#
#   _staging/archive-001/dk-data-files/mol_bronze/mol_bronze__pubchem__abc/
#       pubchem.dump
#
#   _loose_dumps/mol_bronze/
#       mol_bronze__clinicaltrials__def-008.dump
#
# Fixtures are gitignored (see tests/fixtures/prestaged/.gitignore) —
# regenerate locally with:
#
#   PG_URL=postgresql://postgres:postgres@localhost:5432/postgres \
#     bash tests/fixtures/prestaged/generate_fixtures.sh
#
# Requires: pg_dump (postgresql-client-16), access to ANY database
# (the actual content is irrelevant — fixtures only need to be valid
# PGDMP-format files with magic bytes for validate_magic_bytes to pass).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PG_URL="${PG_URL:?must be set to a postgres URL for pg_dump to read from}"

make_dump() {
  local out="$1"
  mkdir -p "$(dirname "$out")"
  # Dump a tiny built-in system view — guaranteed to exist and produce
  # a valid, small .dump file. Content unused by tests.
  pg_dump --dbname="$PG_URL" \
          --format=custom \
          --schema-only \
          --table=pg_catalog.pg_class \
          --file="$out"
  echo "  wrote $out ($(stat -f '%z' "$out" 2>/dev/null || stat -c '%s' "$out") bytes)"
}

echo ">> generating prestaged fixtures in $HERE"

# Raw layout: multi-chunk + retry
make_dump "$HERE/_staging/archive-001/dk-data-files/mol_raw/chembl_sample/1_chembl_sample.dump"
make_dump "$HERE/_staging/archive-001/dk-data-files/mol_raw/chembl_sample/retry_chembl_sample.dump"

# Bronze layout: hashed directory
make_dump "$HERE/_staging/archive-001/dk-data-files/mol_bronze/mol_bronze__pubchem__abc123/pubchem.dump"

# Loose dump
make_dump "$HERE/_loose_dumps/mol_bronze/mol_bronze__clinicaltrials__def456-008.dump"

# A non-dump file to verify the walker ignores it
echo "garbage" > "$HERE/_staging/archive-001/dk-data-files/mol_raw/not_a_dump.txt"

echo ">> ok"
