# Migration Renumber Check — Feature 002

**Feature**: 002-external-integration-foundation (T155, D5)
**Date**: 2026-04-13

## Why

Feature 002 introduces migrations 215, 216, 217, 218, 220, 222. If
another feature lands its own migration at any of those numbers
before feature 002 merges, we need to renumber. This is the
procedure for catching that drift **immediately before merging
feature 002** — not at PR creation time (that number would already
be stale).

## Procedure

Run this check immediately before typing `gh pr merge`:

```bash
cd /Users/pschloz/Desktop/DataKinetic/dk-data-FE
git fetch origin main
LATEST_ON_MAIN=$(git ls-tree -r origin/main --name-only \
  | grep -E '^src/dk_data/sql/migrations/[0-9]+_' \
  | awk -F'/' '{print $NF}' \
  | grep -Eo '^[0-9]+' \
  | sort -n | tail -1)
echo "Highest migration number on main: $LATEST_ON_MAIN"

LATEST_ON_BRANCH=$(ls src/dk_data/sql/migrations/ \
  | grep -Eo '^[0-9]+' \
  | sort -n | tail -1)
echo "Highest migration number on branch: $LATEST_ON_BRANCH"
```

## Decision tree

- `LATEST_ON_MAIN < 215`: safe — merge as-is.
- `LATEST_ON_MAIN in [215, 216, 217, 218, 220, 222]`: **COLLISION**.
  Another feature has already used one of our numbers. Rename
  locally (`git mv`), update every reference (tasks.md, contracts,
  tests), re-run the test suite, then re-run this check.
- `LATEST_ON_MAIN > 222`: safe — our numbers are still above the
  main trunk. But verify none of the numbers 215–222 were used, just
  in case.

## References to update on a rename

If we need to rename 218 → 225 (for example):

- [ ] `src/dk_data/sql/migrations/218_drop_web_anon.sql` → `225_drop_web_anon.sql`
- [ ] `src/dk_data/sql/migrations/218_drop_web_anon_rollback.sql` → `225_drop_web_anon_rollback.sql`
- [ ] `tests/test_218_drop_web_anon.py` → `tests/test_225_drop_web_anon.py`
      (update MIGRATION / ROLLBACK_MIGRATION constants)
- [ ] `.dk/specs/002-external-integration-foundation/tasks.md` — every mention
- [ ] `.dk/specs/002-external-integration-foundation/contracts/migration-ddl.md`
- [ ] `docs/runbooks/rollback-web-anon-drop.md`
- [ ] `docs/reviews/migrations-215-220.md` — per-file checklist header
- [ ] `docs/reports/metric-coverage-audit.md` + any other report that
      mentions the specific number
- [ ] `docs/runbooks/chembl-consolidation.md` / `pubchem-consolidation.md`
      / any runbook that names migration 220 explicitly
- [ ] Commit message prefix `T077` (task ID — DO NOT rename, task IDs
      are stable across renumbering)

## Automation note

This check should be a git hook in a future sprint — a pre-merge
script that rejects the merge if a collision is detected. For now,
it's a manual procedure because the risk is small (single feature,
controlled branch) and the cost of wrong automation is high.

## Related

- `docs/reviews/migrations-215-220.md`
- `src/dk_data/sql/migrations/` — the canonical list
