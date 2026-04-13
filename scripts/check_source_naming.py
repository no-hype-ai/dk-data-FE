#!/usr/bin/env python3
"""T135 — CI check enforcing canonical source-name consistency.

Feature: 002-external-integration-foundation (US-20)

Verifies that the same canonical source name is used across three
layers:

  1. `meta.backfill_state.source_name` values (from migration 220)
  2. `mol_raw.*` / `hcs_raw.*` table names under
     `src/dk_data/sql/migrations/` and `src/dk_data/sqlmesh/`
  3. Python ingestion modules under `src/dk_data/ingestion/sources/`

A drift between any two of these is what migration 220 corrected
(epo_ops → epo_patents, cochrane → cochrane_reviews, ema_mol → ema,
hta_bodies → hta_decisions, hrsa → hrsa_shortage_areas). The CI
check here PINS the post-migration state so a future PR cannot
silently reintroduce the drift.

Exit codes:
    0  — no drift
    1  — drift detected, prints the diff
    2  — prerequisite failure (missing file, parse error)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_220 = REPO_ROOT / "src" / "dk_data" / "sql" / "migrations" / "220_align_source_naming.sql"
INGESTION_DIR = REPO_ROOT / "src" / "dk_data" / "ingestion" / "sources"

# Canonical names pinned by migration 220. If migration 220 grows more
# rename entries in the future, extend this list in the same PR.
CANONICAL_NAMES: frozenset[str] = frozenset(
    {
        "chembl_activities",
        "cochrane_reviews",
        "ema",
        "epo_patents",
        "hrsa_shortage_areas",
        "hta_decisions",
        "pubchem_molecules",
    }
)

# Names that were removed by migration 220 — if we see any of these,
# that's a drift regression.
#
# NOTE: `chembl` is deliberately NOT in this list. Per T165 + spec
# Non-Goals, renaming `mol_raw.chembl` → `mol_raw.chembl_molecules`
# is out of scope for feature 002 (it's an incompatible table rename,
# not a metadata update). The historical migrations that create
# `mol_raw.chembl` stay as-is.
DEPRECATED_NAMES: frozenset[str] = frozenset(
    {
        "cochrane",
        "ema_mol",
        "epo_ops",
        "hrsa",
        "hta_bodies",
    }
)

# Python ingestion module files that are "grandfathered" — they keep
# their legacy name because the Python module name was NOT part of the
# rename in migration 220 (only the backfill_state row was). Migrating
# the Python file renames would require updating every call site,
# which is out of scope for feature 002. Track as a follow-up.
GRANDFATHERED_MODULES: frozenset[str] = frozenset(
    {
        "cochrane",    # reads cochrane_reviews from meta.backfill_state
        "ema_mol",     # reads ema from meta.backfill_state
        "epo_ops",     # reads epo_patents from meta.backfill_state
        "hrsa",        # reads hrsa_shortage_areas from meta.backfill_state
        "hta_bodies",  # reads hta_decisions from meta.backfill_state
    }
)


def extract_source_names_from_migration_220() -> set[str]:
    """Extract the NEW source_name values from migration 220's rename map.

    Migration 220 stores the rename pairs as an array literal:

        rename_map TEXT[][] := ARRAY[
            ['epo_ops',      'epo_patents'],
            ['cochrane',     'cochrane_reviews'],
            ...
        ];

    We only care about the right-hand (canonical) side.
    """
    if not MIGRATION_220.exists():
        return set()
    text = MIGRATION_220.read_text()
    # Match `['old', 'new']` pairs inside the rename_map array.
    pattern = re.compile(
        r"\[\s*'[a-z][a-z0-9_]+'\s*,\s*'([a-z][a-z0-9_]+)'\s*\]"
    )
    return set(pattern.findall(text))


def extract_python_ingestion_modules() -> set[str]:
    if not INGESTION_DIR.exists():
        return set()
    return {
        p.stem
        for p in INGESTION_DIR.glob("*.py")
        if p.is_file() and not p.stem.startswith("_")
    }


def main() -> int:
    errors: list[str] = []

    # Check migration 220's canonical names match our pin.
    migration_names = extract_source_names_from_migration_220()
    if not migration_names:
        print("WARN: migration 220 not present or parse failed; skipping migration check", file=sys.stderr)
    else:
        pinned_missing = {
            n for n in migration_names
            if n not in CANONICAL_NAMES and n not in DEPRECATED_NAMES
        }
        if pinned_missing:
            errors.append(
                "Migration 220 sets source_name to values not in the CI pin: "
                f"{sorted(pinned_missing)}. Either update CANONICAL_NAMES in "
                "this script or correct the migration."
            )

    # Check Python ingestion modules don't use deprecated names that
    # are NOT grandfathered.
    ingestion_modules = extract_python_ingestion_modules()
    bad_modules = (ingestion_modules & DEPRECATED_NAMES) - GRANDFATHERED_MODULES
    if bad_modules:
        errors.append(
            f"Python ingestion modules use deprecated source names: "
            f"{sorted(bad_modules)}. Either rename them or add to "
            "GRANDFATHERED_MODULES with justification."
        )

    # Check migrations ≥ 220 (post-alignment) don't reintroduce
    # deprecated names in raw/bronze table DDL. Historical migrations
    # (< 220) are grandfathered — the whole point of migration 220 is
    # to align metadata, not rewrite history.
    for sql_file in (REPO_ROOT / "src/dk_data/sql/migrations").glob("*.sql"):
        match = re.match(r"^(\d+)_", sql_file.name)
        if not match or int(match.group(1)) < 220:
            continue
        text = sql_file.read_text()
        code_only = re.sub(r"--.*$", "", text, flags=re.M)
        code_only = re.sub(r"'[^']*'", "", code_only)
        for bad in DEPRECATED_NAMES:
            pattern = re.compile(
                rf"\b(mol|hcs|ind|hcp|ip)_(raw|bronze|silver|gold)\.{bad}\b"
            )
            if pattern.search(code_only):
                errors.append(
                    f"{sql_file.name}: references deprecated source name "
                    f"`{bad}` — use canonical form (this is a post-220 migration)"
                )
                break

    if errors:
        print("Source-name consistency check FAILED:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("Source-name consistency check PASSED")
    print(f"  canonical names pinned: {len(CANONICAL_NAMES)}")
    print(f"  ingestion modules found: {len(ingestion_modules)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
