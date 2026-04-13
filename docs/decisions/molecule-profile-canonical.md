# Decision: Canonical `molecule_profile` table

**Feature**: 002-external-integration-foundation (US-10, T137)
**Date**: 2026-04-13
**Status**: Decided — canonical is `mol_gold.molecule_profile` (singular)

## Context

During the feature 002 scope audit we found two tables with confusingly
similar names:

| Table | Created by | Used by |
|---|---|---|
| `mol_gold.molecule_profile` (singular) | migration 081 | Conditional `api.molecule_properties` view, `molecules.getProfile` adapter method, feature 002 contracts |
| `mol_gold.molecule_profiles` (plural) | migration 020 | Legacy CMS analytics pipeline, `mart.molecule_360` (unused since 2025-11) |

Both still exist in production. Different migrations populate them.
Different consumers query them. The original brief assumed only one
existed — this is a known hazard captured in
`.dk/memory/lessons.md` → "Two tables with confusingly similar names".

## Decision

**Canonical table = `mol_gold.molecule_profile` (singular).**

Reasons:

1. **Actively maintained**: SQLMesh models the singular form in
   `src/dk_data/sqlmesh/models/molecules/gold/molecule_profile.sql`.
   The plural form has no SQLMesh model — it's a static snapshot.
2. **Used by the read surface that ships in feature 002**: the
   `api.molecule_properties` view and `molecules.getProfile` adapter
   method both read the singular form.
3. **Smaller blast radius to drop**: the plural form has exactly one
   consumer (`mart.molecule_360`) which has been unused since
   2025-11-01 (verified via `pg_stat_user_tables.last_seq_scan`).

## Consequences

- Migration 222 (T138) drops `mol_gold.molecule_profiles` and
  `mart.molecule_360` entirely, after a 14-day grace period.
- No consumer of the plural form needs a code change (none are active).
- The project convention for future gold tables is **singular noun**
  (one row per molecule, one row per company, etc.). This is recorded
  in the "Silver Hub Architecture" section of `CLAUDE.md` as a
  follow-up.
- `CLAUDE.md` schema section must be updated to call out the
  singular convention explicitly to prevent the next pair of
  confusing tables from being created.

## Alternatives considered

- **Keep both**: rejected — the names are so close that the next
  operator is guaranteed to query the wrong one. This is a footgun
  that will definitely misfire.
- **Rename `mol_gold.molecule_profile` → `mol_gold.molecule_profile_v2`**:
  rejected — adds a version suffix where none was needed, doesn't
  solve the underlying ambiguity, and breaks every existing query.
- **Merge the two tables** (UNION the rows): rejected — the plural
  form has stale columns that aren't in the canonical schema; merging
  would require re-deriving every row.

## Migration plan

1. (Now) Mark `mol_gold.molecule_profiles` with a deprecation COMMENT
   pointing at the singular form. — covered by migration 222.
2. (Day 0 → Day 14) Wait 14 days. Re-check `pg_stat_user_tables` on
   Day 14 — any read against the plural form is an owner we missed
   and needs a talk.
3. (Day 14+) Drop the plural table + `mart.molecule_360` in a follow-up
   migration. This is separate from feature 002 to keep blast radii
   small.

## Related

- `.dk/memory/lessons.md` — "Two tables with confusingly similar names"
- `src/dk_data/sqlmesh/models/molecules/gold/molecule_profile.sql`
- `src/dk_data/sql/migrations/020_mol_schemas.sql` — original plural
- `src/dk_data/sql/migrations/081_gold_molecule_profile.sql` — canonical singular
