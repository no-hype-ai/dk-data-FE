# Contract: writes to `meta.transform_runs`

## Purpose

This feature treats `meta.transform_runs` as the single source of truth for run state (FR-009). This contract documents what the writer guarantees regardless of external observability state.

## Column discovery

At connection time, the writer issues:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_schema='meta' AND table_name='transform_runs';
```

and builds a mapping from canonical names (below) to actual names (handles P3 schema drift: `status` vs `state` vs `run_status`).

## Canonical columns written

| Canonical name | Type | Notes |
|----------------|------|-------|
| `run_id` | text | Deterministic hash (R4) |
| `schema` | text | Target schema |
| `table` | text | Target table |
| `source_kind` | text | pg_dump / bronze_ready / raw_csv / live_fetch |
| `status` | text | pending / running / completed / failed / blocked / skipped_view / no_source_available |
| `row_count` | bigint | post-restore `COUNT(*)`; NULL pre-completion |
| `started_at` | timestamptz | On transition to `running` |
| `finished_at` | timestamptz | On any terminal status |
| `artifact_sha256` | text | Comma-joined, or NULL for live_fetch |
| `error_detail` | text | Truncated to 4 KB |

If a canonical column is absent in the actual schema, the writer logs a warning once and drops the value (forward-compatible behavior; no crash).

## Uniqueness

`UNIQUE (run_id, schema, "table")` — enforced application-side via `INSERT ... ON CONFLICT DO UPDATE`.

## State transitions

Only these transitions are legal; the writer rejects others:

```
pending   -> running, blocked, no_source_available, skipped_view
running   -> completed, failed
(terminal states are not re-entered)
```

## Guarantees

- Every step reaches a terminal state before the job exits (FR-009).
- No write to `meta.transform_runs` depends on alloy, OTLP, MinIO, or opensearch being healthy.
- OTLP emission is best-effort, wrapped in `try/except` with a single logged warning on failure.
