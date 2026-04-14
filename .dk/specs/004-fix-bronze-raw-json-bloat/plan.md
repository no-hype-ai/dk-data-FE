# Implementation Plan: Fix Bronze Raw JSON Storage Bloat

## Technical Context

- **Language**: SQL (SQLMesh models)
- **Platform**: PostgreSQL 16, SQLMesh, CloudNativePG on k3s
- **Affected Files**:
  - `src/dk_data/sqlmesh/models/molecules/bronze/rxnorm_concepts.sql` (4 line changes)
  - `src/dk_data/sqlmesh/models/molecules/bronze/purple_book.sql` (1 line change)
- **Testing**: SQLMesh plan --dry-run, grep for downstream raw_json references
- **Dependencies**: None — isolated SQL changes, no package or infra changes

## Project Structure (affected files only)

```
src/dk_data/sqlmesh/models/molecules/bronze/
├── rxnorm_concepts.sql    ← 4 raw_json assignments to fix (lines 29, 46, 64, 82)
└── purple_book.sql        ← 1 raw_json assignment to fix (line 58)
```

## Implementation Details

### rxnorm_concepts.sql — 4 changes

| CTE | Current (line) | Fix |
|-----|---------------|-----|
| from_id_group | `r.response_body AS raw_json` (L29) | `r.response_body->'idGroup' AS raw_json` |
| from_properties | `r.response_body AS raw_json` (L46) | `r.response_body->'properties' AS raw_json` |
| from_min_concept | `r.response_body AS raw_json` (L64) | `concept AS raw_json` |
| from_related | `r.response_body AS raw_json` (L82) | `prop AS raw_json` |

### purple_book.sql — 1 change

| Location | Current (line) | Fix |
|----------|---------------|-----|
| Main SELECT | `response_body AS raw_json` (L58) | `prod AS raw_json` |

## Verification

1. Grep all silver/gold models for references to `raw_json` from these two bronze tables — confirm zero hits
2. SQLMesh plan to verify SQL validity
3. Compare row counts before/after to confirm no data loss
