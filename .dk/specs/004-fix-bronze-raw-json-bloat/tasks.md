# Tasks: Fix Bronze Raw JSON Storage Bloat

## Phase 1: Fix Models

- [ ] T001 [P] [US1] Fix raw_json in from_id_group CTE — change `r.response_body AS raw_json` to `r.response_body->'idGroup' AS raw_json` at line 29 in `src/dk_data/sqlmesh/models/molecules/bronze/rxnorm_concepts.sql`
- [ ] T002 [P] [US1] Fix raw_json in from_properties CTE — change `r.response_body AS raw_json` to `r.response_body->'properties' AS raw_json` at line 46 in `src/dk_data/sqlmesh/models/molecules/bronze/rxnorm_concepts.sql`
- [ ] T003 [P] [US1] Fix raw_json in from_min_concept CTE — change `r.response_body AS raw_json` to `concept AS raw_json` at line 64 in `src/dk_data/sqlmesh/models/molecules/bronze/rxnorm_concepts.sql`
- [ ] T004 [P] [US1] Fix raw_json in from_related CTE — change `r.response_body AS raw_json` to `prop AS raw_json` at line 82 in `src/dk_data/sqlmesh/models/molecules/bronze/rxnorm_concepts.sql`
- [ ] T005 [P] [US2] Fix raw_json in purple_book — change `response_body AS raw_json` to `prod AS raw_json` at line 58 in `src/dk_data/sqlmesh/models/molecules/bronze/purple_book.sql`

## Phase 2: Verification

- [ ] T006 [US3] Verify no downstream model references raw_json from mol_bronze.rxnorm or mol_bronze.purple_book — grep all silver/gold SQL models
- [ ] T007 Validate SQL syntax by running SQLMesh plan dry-run (if available) or manual SQL parse check

## Dependency Graph

```
T001, T002, T003, T004 (parallel) ─┐
T005 (parallel) ───────────────────┤
                                    ├─→ T006 → T007
```

## Implementation Strategy

All T001-T005 are single-line edits in two files, fully parallelizable. T006 and T007 are verification steps that depend on the edits being complete.
