-- Feature: 005-prestaged-hydration
--
-- Adds `status text` and `details jsonb` columns to `meta.transform_runs`,
-- plus two indexes that the hydration writer and the platform-api metrics
-- query need.
--
-- Why this is needed: the hydration feature (see
-- .dk/specs/005-prestaged-hydration/) writes one row per source per run
-- to meta.transform_runs and uses a deterministic `run_label` to make
-- reruns idempotent. Before this migration, the only columns available
-- were (run_id autoincrement, procedure_name, chunk_position, started_at,
-- ended_at, rows_processed, wal_bytes) — none of which can carry the
-- outcome state (`completed`/`failed`/`blocked`/`skipped_view`/
-- `no_source_available`) or the run label.
--
-- This migration also closes the P3 prerequisite documented in plan.md:
-- the platform-api `/metrics` endpoint polls meta.transform_runs roughly
-- every 30s and errors with `column "status" does not exist`. After
-- this migration the column exists and the error clears without any
-- platform-api code change (the column is nullable, so rows written by
-- the old bootstrap procedures keep working untouched).
--
-- Scope of change:
--   1. ALTER TABLE meta.transform_runs ADD COLUMN status text — NULL-able
--   2. ALTER TABLE meta.transform_runs ADD COLUMN details jsonb — NULL-able
--   3. Backfill every pre-migration row with status='legacy' so the
--      platform-api NOT NULL assertions (if any) see a value.
--   4. CREATE INDEX meta_transform_runs_status_idx (partial, WHERE NOT NULL)
--   5. CREATE INDEX meta_transform_runs_run_label_idx on (details->>'run_label')
--
-- View safety: meta.transform_runs is a real table (relkind='r' verified
-- via pg_class on 2026-04-14). The migration 227 lesson — that
-- information_schema.tables includes views — does not bite here because
-- we hard-code the one target table rather than iterating.
--
-- Idempotent: every statement uses IF NOT EXISTS / WHERE status IS NULL
-- so re-running the migration is a no-op.
--
-- Transactional: single explicit BEGIN/COMMIT; every statement is
-- DDL-under-transaction-safe. No VACUUM, no CLUSTER.

BEGIN;

SET LOCAL statement_timeout = '120s';
SET LOCAL lock_timeout = '10s';

-- -----------------------------------------------------------------------------
-- 1. New columns
-- -----------------------------------------------------------------------------
-- Both are nullable. The hydration writer always populates them; legacy
-- writers (source_backfill.py chunked bootstraps) do not, and that's fine.

ALTER TABLE meta.transform_runs
  ADD COLUMN IF NOT EXISTS status  text,
  ADD COLUMN IF NOT EXISTS details jsonb;

-- -----------------------------------------------------------------------------
-- 2. Backfill
-- -----------------------------------------------------------------------------
-- Pre-migration rows get status='legacy' so any platform-api query that
-- treats status as NOT NULL sees a stable value. Details stays NULL — the
-- legacy rows carry no run_label and shouldn't pollute the run_label index.

UPDATE meta.transform_runs
   SET status = 'legacy'
 WHERE status IS NULL;

-- -----------------------------------------------------------------------------
-- 3. Indexes
-- -----------------------------------------------------------------------------
-- status_idx: partial — excludes the ~100% of rows that are 'legacy' and
-- any future NULL rows, keeping the index small. Used by the platform-api
-- metrics path ("how many runs failed in the last hour?").

CREATE INDEX IF NOT EXISTS meta_transform_runs_status_idx
    ON meta.transform_runs (status)
 WHERE status IS NOT NULL
   AND status <> 'legacy';

-- run_label_idx: expression index on the JSONB `run_label` field. The
-- hydration writer's skip-if-complete query is:
--   SELECT 1 FROM meta.transform_runs
--    WHERE details->>'run_label' = :label
--      AND procedure_name = :proc
--      AND status = 'completed';
-- This index makes that O(log n) for the label match; the
-- procedure_name/started_at composite already exists.

CREATE INDEX IF NOT EXISTS meta_transform_runs_run_label_idx
    ON meta.transform_runs ((details ->> 'run_label'))
 WHERE details ? 'run_label';

COMMIT;
