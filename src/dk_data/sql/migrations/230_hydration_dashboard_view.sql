-- Feature: 005-prestaged-hydration (Stage 7 supplement)
--
-- Adds three read-only views over `meta.transform_runs` and `meta.wal_usage`
-- so a single-file HTML dashboard can poll PostgREST and watch the
-- prod hydration progress without operators tailing logs.
--
-- Why this is needed: Stage 8 runs ~6 hours, restoring 120 dumps across
-- 60+ sources. Operators need a glanceable view of what's done, what's
-- in flight, and whether WAL pressure is staying under the 70% ceiling.
-- These views aggregate the writer's terminal-state rows into the
-- shapes the dashboard renders.
--
-- Scope:
--   1. meta.hydration_dashboard — per-source latest terminal state for
--      the most recent run_label
--   2. meta.hydration_summary — count by status for the most recent run
--   3. meta.hydration_wal — last 60 wal_usage observations
--   4. GRANT SELECT on all three to api_user (PostgREST exposure)
--
-- View safety: meta.transform_runs and meta.wal_usage are real tables/views
-- that already exist. relkind check not needed; we are CREATE OR REPLACE
-- VIEWs, not ALTER TABLE.
--
-- Idempotent: CREATE OR REPLACE + GRANT are safe to re-run.
--
-- Transactional: explicit BEGIN/COMMIT; pure DDL.

BEGIN;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '5s';

-- ---------------------------------------------------------------------------
-- 1. meta.hydration_dashboard — per-source latest state of the active run
-- ---------------------------------------------------------------------------
-- "Active run" = the most recent run_label seen in meta.transform_runs.
-- Idempotency means re-runs reuse the same run_label, so this view stays
-- coherent across restarts of the same hydration run.

CREATE OR REPLACE VIEW meta.hydration_dashboard AS
WITH latest_run AS (
    SELECT details ->> 'run_label' AS run_label
      FROM meta.transform_runs
     WHERE details ? 'run_label'
     ORDER BY ended_at DESC NULLS LAST
     LIMIT 1
)
SELECT
    tr.run_id,
    tr.procedure_name,
    tr.details ->> 'target_schema'   AS target_schema,
    tr.details ->> 'target_table'    AS target_table,
    tr.details ->> 'source_kind'     AS source_kind,
    tr.status,
    tr.rows_processed,
    tr.wal_bytes,
    tr.started_at,
    tr.ended_at,
    EXTRACT(EPOCH FROM (tr.ended_at - tr.started_at)) AS duration_s,
    tr.details ->> 'error_detail'    AS error_detail,
    tr.details ->> 'artifact_sha256' AS artifact_sha256,
    lr.run_label
  FROM meta.transform_runs tr
  CROSS JOIN latest_run lr
 WHERE tr.details ->> 'run_label' = lr.run_label
 ORDER BY tr.started_at DESC NULLS LAST;

COMMENT ON VIEW meta.hydration_dashboard IS
    'Per-source latest terminal state for the most recent hydration run. '
    'Powered by feature 005-prestaged-hydration. Safe to query at any '
    'frequency; backed by meta_transform_runs_run_label_idx.';

-- ---------------------------------------------------------------------------
-- 2. meta.hydration_summary — status counts + total rows for active run
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW meta.hydration_summary AS
SELECT
    COALESCE(status, 'unknown') AS status,
    count(*)                    AS n,
    COALESCE(sum(rows_processed), 0) AS total_rows,
    max(ended_at)               AS most_recent_at
  FROM meta.hydration_dashboard
 GROUP BY 1
 ORDER BY 1;

COMMENT ON VIEW meta.hydration_summary IS
    'Status histogram for the most recent hydration run. Drives the '
    'doughnut chart in dashboards/hydration-dashboard.html.';

-- ---------------------------------------------------------------------------
-- 3. meta.hydration_wal — recent per-chunk WAL write events
-- ---------------------------------------------------------------------------
-- meta.wal_usage tracks per-chunk writes (recorded_at, procedure_name,
-- chunk_index, wal_bytes, rows_processed, duration_ms, pod_name,
-- exceeded_limit). It is NOT a live WAL-pressure timeline. We expose
-- the most recent 60 writes so the dashboard can show write throughput
-- and any rows where exceeded_limit=true.

CREATE OR REPLACE VIEW meta.hydration_wal AS
SELECT
    recorded_at AS observed_at,                         -- alias for dashboard compatibility
    procedure_name,
    chunk_index,
    wal_bytes,
    rows_processed,
    duration_ms,
    pod_name,
    exceeded_limit,
    -- Synthetic "pct_used" so the dashboard's sparkline still has
    -- something to plot. Maps wal_bytes against the legacy 2 GB
    -- per-write soft ceiling: 100% means we hit 2 GB on a single chunk.
    -- This is NOT a live WAL-pressure measurement (no such view exists).
    LEAST(100.0::numeric, (wal_bytes::numeric / 2147483648.0) * 100.0)
        AS pct_used
  FROM meta.wal_usage
 ORDER BY recorded_at DESC
 LIMIT 60;

COMMENT ON VIEW meta.hydration_wal IS
    'Most-recent 60 per-chunk WAL write events from meta.wal_usage. '
    'pct_used is synthetic: wal_bytes / 2GB * 100, capped at 100. '
    'Drives the sparkline in dashboards/hydration-dashboard.html.';

-- ---------------------------------------------------------------------------
-- 4. PostgREST exposure — GRANT SELECT to api_user
-- ---------------------------------------------------------------------------
-- The PostgREST role is api_user (per migration 228). Grant USAGE on
-- meta first if not already granted, then SELECT on the three views.

GRANT USAGE  ON SCHEMA meta TO api_user;
GRANT SELECT ON meta.hydration_dashboard TO api_user;
GRANT SELECT ON meta.hydration_summary   TO api_user;
GRANT SELECT ON meta.hydration_wal       TO api_user;

COMMIT;
