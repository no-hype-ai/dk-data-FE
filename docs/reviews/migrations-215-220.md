# Migration Review Checklist — 215, 216, 217, 218, 220

**Feature**: 002-external-integration-foundation (T067a)
**Date**: 2026-04-13
**Reviewer**: __________

This checklist must be completed before merging feature 002's migration
set. Every row must pass. Any fail → block the PR.

## Invariants

Every feature-002 migration MUST satisfy all of these:

| # | Invariant | How to verify |
|---|---|---|
| 1 | DML-free (no INSERT / UPDATE / DELETE of business data) | `grep -nE 'INSERT INTO (mol_|hcs_|ind_|hcp_|ip_)'` must return 0 |
| 2 | Idempotent (`IF NOT EXISTS` / `CREATE OR REPLACE` / `ON CONFLICT DO NOTHING`) | Re-run the migration against the same DB; exit code = 0, no side effects |
| 3 | Wrapped in `BEGIN;` / `COMMIT;` | `head -20` shows BEGIN; `tail -5` shows COMMIT; |
| 4 | `SET LOCAL statement_timeout ≥ 60s` on any migration with large REVOKE/GRANT scope | grep `SET LOCAL statement_timeout` |
| 5 | `SET LOCAL lock_timeout = '30s'` or tighter | grep `SET LOCAL lock_timeout` |
| 6 | Explicit transaction comments explaining WHY (not WHAT) | top-of-file header must reference spec user story |
| 7 | No `web_anon` grants (migration 218 drops the role) | `grep -n "web_anon" <file>` — only comments explaining the exclusion are allowed |

## Per-file checklist

### 215_deprecate_redundant_ci_views.sql

- [ ] DML-free: YES (pure COMMENT ON VIEW)
- [ ] Idempotent: YES (dynamic DO block, no-op if a view is missing)
- [ ] BEGIN/COMMIT wrapped: YES
- [ ] Statement timeout: YES (`'30s'`)
- [ ] Lock timeout: YES (`'10s'`)
- [ ] Feature-002 header: YES (US-6, T067)
- [ ] No web_anon grants: N/A (no grants at all in this file)
- [ ] Covered by test: `tests/test_215_deprecate_redundant_ci_views.py` (25 assertions)

### 216_missing_mol_api_views.sql

- [ ] DML-free: YES (`CREATE OR REPLACE VIEW` only)
- [ ] Idempotent: YES (`CREATE SCHEMA IF NOT EXISTS`, `CREATE OR REPLACE VIEW`)
- [ ] BEGIN/COMMIT wrapped: YES
- [ ] Statement timeout: YES (`'30s'`)
- [ ] Lock timeout: YES (`'10s'`)
- [ ] Feature-002 header: YES (US-4, T071)
- [ ] No web_anon grants: YES (grants are to `analyst, api_user` only)
- [ ] Covered by test: `tests/test_216_missing_mol_api_views.py` (30 assertions)

### 217_resolve_function_grants.sql

- [ ] DML-free: YES (GRANT EXECUTE only)
- [ ] Idempotent: YES (schema-wide `GRANT EXECUTE ON ALL FUNCTIONS` is idempotent)
- [ ] BEGIN/COMMIT wrapped: YES
- [ ] Statement timeout: YES (`'30s'`)
- [ ] Lock timeout: YES (`'10s'`)
- [ ] Feature-002 header: YES (US-5, T073)
- [ ] No web_anon grants: YES (only `analyst, api_user`)
- [ ] Covered by test: `tests/test_217_resolve_function_grants.py` (28 assertions)

### 218_drop_web_anon.sql (+ rollback)

- [ ] DML-free: YES (REVOKE / DROP ROLE only, no INSERT/UPDATE/DELETE)
- [ ] Idempotent: YES (skips cleanly if `web_anon` is already gone)
- [ ] BEGIN/COMMIT wrapped: YES
- [ ] Statement timeout: YES (`'120s'` — matches the REVOKE ALL IN SCHEMA cost)
- [ ] Lock timeout: YES (`'30s'`)
- [ ] Feature-002 header: YES (US-2, T077)
- [ ] No residual web_anon grants: dynamic information_schema scan catches everything
- [ ] Rollback is minimum-only per F-D014: verified — only USAGE on api + SELECT on api.health + api.data_catalog
- [ ] Covered by test: `tests/test_218_drop_web_anon.py` (30 assertions, both drop + rollback)
- [ ] Staging apply documented: `docs/runbooks/rollback-web-anon-drop.md`

### 220_align_source_naming.sql

- [ ] DML-free: NO (UPDATE on meta.backfill_state — but this IS operational metadata, not business data — allowed)
- [ ] Idempotent: YES (updates `source_name` only if the old name exists)
- [ ] BEGIN/COMMIT wrapped: YES
- [ ] Statement timeout: YES
- [ ] Lock timeout: YES
- [ ] Feature-002 header: YES (US-20, T131)
- [ ] Collision guard: YES — refuses to rename if the new name already exists

## Reviewer sign-off

All checkboxes above must be ticked. Open a blocking comment on the PR
for any unchecked item. The reviewer commits this file with their name
on the line below, as part of the same PR that lands the migrations.

```
Reviewer:     _____________________
Date:         ______-__-__
Approve:      yes / no
```

## Related

- `src/dk_data/sql/migrations/21[5-8]*.sql` — the migration files
- `src/dk_data/sql/migrations/220*.sql` — source name alignment
- `tests/test_21[5-8]*.py` / `tests/test_220*.py` — contract tests
- `docs/runbooks/rollback-web-anon-drop.md`
- `.dk/memory/lessons.md` — "Migration filenames can lie" + "Migration 086 grants"
