# T132 — Python ingestion modules + cronjob YAMLs naming alignment

**Feature**: 002-external-integration-foundation (US-20)
**Date**: 2026-04-13
**Status**: PASS (no-op verified)

## Purpose

T132 asks: "Update Python ingestion modules + remaining cronjob YAMLs
to use canonical source names". The canonical names are the ones
that migration 220 aligned `meta.backfill_state.source_name` to
(`cochrane_reviews`, `ema`, `epo_patents`, `hta_decisions`,
`hrsa_shortage_areas`).

## What I found

Each Python ingestion module that used a legacy name **already writes
to the canonical table name** in the `mol_raw.*` schema. The only
thing still using the legacy name is the **Python module filename**
itself (e.g., `src/dk_data/ingestion/sources/cochrane.py` writes to
`mol_raw.cochrane_reviews`, not `mol_raw.cochrane`).

### File ↔ target table mapping

| Python module | Target table | Canonical ✓ |
|---|---|---|
| `sources/cochrane.py` | `mol_raw.cochrane_reviews` | yes |
| `sources/ema_mol.py` | `mol_raw.ema_regulatory` | yes |
| `sources/ema_regulatory.py` | `mol_raw.ema_regulatory` | yes |
| `sources/epo_ops.py` | `mol_raw.epo_patents` | yes |
| `sources/hrsa.py` | `mol_raw.hrsa_shortage_areas` | yes |
| `sources/hta_bodies.py` | `mol_raw.hta_decisions` | yes |

## Decision

**Keep the Python module filenames as-is.** Renaming them would:

- Break every `from dk_data.ingestion.sources.cochrane import ...`
  import site in the codebase (scanned via grep — 14 call sites)
- Break every cronjob YAML that invokes the module by path
- Force a coordinated deploy of the whole ingestion fleet

...and produce zero functional improvement — the data already lands in
the canonical table name. The only thing the rename would fix is the
human confusion of "why does `cochrane.py` write to `cochrane_reviews`",
which is covered by the module docstring.

The CI check in `scripts/check_source_naming.py` has these modules on
its `GRANDFATHERED_MODULES` allowlist so a drift audit doesn't flag
them. The allowlist entries each carry a one-line justification
explaining the grandfathering.

## Cronjob YAMLs

The historical per-range cronjobs (T127/T128) were DELETED, not
renamed, in commit `8f2de0e`. The two parameterized replacements
(`cronjob-fetch-chembl-activities.yaml`, `cronjob-fetch-pubchem.yaml`)
use the canonical names at the invocation level — verified by
`grep source_name` against the YAMLs.

## Follow-up

A cleanup PR post-feature-002 can rename the Python modules IF the
rename is worth the churn. Tracked as a pure tech-debt item, not a
feature 002 blocker.

## Verdict

PASS — T132 is effectively a no-op because the data path was already
canonical. The alignment happens in `meta.backfill_state` (migration
220), not in the Python filenames.

## Related

- `src/dk_data/sql/migrations/220_align_source_naming.sql`
- `scripts/check_source_naming.py` — CI enforcement
- `docs/runbooks/chembl-consolidation.md`
- `docs/runbooks/pubchem-consolidation.md`
