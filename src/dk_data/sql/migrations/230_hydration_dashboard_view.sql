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
-- 3. meta.hydration_wal — recent WAL pressure observations
-- ---------------------------------------------------------------------------
-- Reads from the existing meta.wal_usage view (added in commit 3b1c1e7).
-- Limits to the last 60 rows so the sparkline stays bounded.

CREATE OR REPLACE VIEW meta.hydration_wal AS
SELECT observed_at, current_wal_bytes, max_wal_size, pct_used
  FROM meta.wal_usage
 ORDER BY observed_at DESC
 LIMIT 60;

COMMENT ON VIEW meta.hydration_wal IS
    'Most-recent 60 WAL pressure observations. Drives the sparkline '
    'in the hydration dashboard. 70% red line, 40% green line.';

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
