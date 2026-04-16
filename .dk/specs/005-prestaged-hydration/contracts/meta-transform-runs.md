# Contract: writes to `meta.transform_runs`

## Purpose

This feature treats `meta.transform_runs` as the single source of truth for hydration run state (FR-009). This contract documents the post-migration-229 schema and exactly how the writer uses it.

## Actual schema (post migration 229)

Verified against `dk-data-prod` on 2026-04-14 and extended by `229_transform_runs_status_details.sql`:

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `run_id` | bigint (bigserial) | NOT NULL | Autoincrement; per-row primary key — NOT our idempotency key |
| `procedure_name` | text | NOT NULL | Writer sets `'prestaged:{target_schema}.{target_table}'` |
| `chunk_position` | text | NOT NULL | Writer sets `str(chunk_index)` ('0', '1', …, 'retry') or `'-'` for single-chunk |
| `started_at` | timestamptz | NOT NULL | On transition to `running` |
| `ended_at` | timestamptz | NOT NULL | On any terminal status |
| `rows_processed` | bigint | NOT NULL | Post-restore `COUNT(*)`; 0 on failure |
| `wal_bytes` | bigint | NOT NULL | Measured via `pg_current_wal_lsn()` brackets; 0 if unmeasured |
| `status` | text | NULL | Added by migration 229. Values: `pending` / `running` / `completed` / `failed` / `blocked` / `skipped_view` / `no_source_available` |
| `details` | jsonb | NULL | Added by migration 229. Carries `{run_label, source_kind, target_schema, target_table, artifact_sha256, error_detail}` |

### Indexes (relevant)

- `transform_runs_pkey` on `run_id`
- `meta_transform_runs_procedure_started_idx` on `(procedure_name, started_at)` — makes the "most recent run for this table" query fast
- `meta_transform_runs_wal_bytes_large_idx` on `(wal_bytes) WHERE wal_bytes > 500000000` — pre-existing
- `meta_transform_runs_status_idx` on `(status) WHERE status IS NOT NULL` — added by 229
- `meta_transform_runs_run_label_idx` on `((details->>'run_label'))` — added by 229 for idempotency lookups

## Writer behavior

### Idempotency query (FR-011)

```sql
SELECT 1 FROM meta.transform_runs
 WHERE details->>'run_label' = %s
   AND procedure_name = %s
   AND status = 'completed'
 LIMIT 1;
```

If returns a row, the writer skips dispatching the step. A `pg_restore` subprocess is NEVER spawned for a source with a `completed` row matching the current `run_label`.

### Upsert on terminal transition

```sql
INSERT INTO meta.transform_runs
  (procedure_name, chunk_position, started_at, ended_at,
   rows_processed, wal_bytes, status, details)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb);
```

No `ON CONFLICT` clause — `run_id` is autoincrement, so every call inserts a fresh row. Historical rows for the same `(procedure_name, run_label)` are preserved for audit.

### details JSONB shape

```json
{
  "run_label": "<64-char hex hash of sorted artifact sha256s + cluster fp>",
  "source_kind": "pg_dump | bronze_ready | raw_csv | live_fetch",
  "target_schema": "<schema name>",
  "target_table": "<table name>",
  "artifact_sha256": "<comma-joined sha256s, or null for live_fetch>",
  "error_detail": "<truncated stderr ≤4 KB, or null>"
}
```

`run_label` is the only field the idempotency path reads. Everything else is for post-hoc analysis.

## State transitions

Recorded by writing new rows; earlier rows are not updated.

```
pending (optional — writer may skip straight to running)
running   → completed | failed
running   → blocked             (upstream failure detected mid-run)
(never written, decided pre-dispatch) → skipped_view | no_source_available
```

Terminal states: `completed`, `failed`, `blocked`, `skipped_view`, `no_source_available`.

## Guarantees

- Every step reaches a terminal state before the job exits (FR-009).
- No write depends on alloy, OTLP, MinIO, or opensearch being healthy.
- OTLP emission is wrapped in `try/except` with a single WARN log on failure.
- Migration 229 is additive with NULL defaults; any existing writer outside this feature continues to work unchanged (`status`/`details` stay NULL for non-hydration runs).
