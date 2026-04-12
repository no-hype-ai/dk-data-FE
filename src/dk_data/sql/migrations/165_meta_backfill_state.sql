-- Migration 165: meta.backfill_state — orchestrator state machine for incremental backfills
-- Feature: 001-silver-medallion-rebuild (audit followup 2026-04-12)
--
-- Replaces the manual `job-initial-backfill.yaml` operator-driven flow with a
-- cron-driven state machine that ticks one source forward per orchestrator run.
--
-- Design:
--   - One row per data source that needs historical backfill
--   - Orchestrator picks ONE source per tick (highest priority, oldest last_success)
--   - Circuit breakers gate execution: cluster busy / WAL budget exhausted / another
--     backfill already running / consecutive failures
--   - Each chunk runs the existing fetcher (e.g. `python -m dk_data.ingestion.main
--     <source> --days-back N`), which already has checkpoint/resume via
--     meta.fetch_checkpoints
--   - The orchestrator just decides WHEN and WHICH; the fetcher decides HOW MUCH
--     per invocation (bounded by activeDeadlineSeconds on the orchestrator pod)
--   - Termination signal: total_rows_loaded >= expected_min_rows OR 3 successful
--     no-op runs in a row (the fetcher's checkpoint indicates no more pages)
--
-- Cluster parallelism analysis (per transformation-reliability-low-tech-solutions.md
-- §1 + §9): the postgres pod has 2 vCPU shared with BLAI (~30%) + litellm (~10%).
-- That leaves ~60% = 1.2 vCPU for dk-data. A single chunked fetcher with
-- SET LOCAL work_mem='128MB' uses 0.5–1 vCPU. So 1 concurrent backfill worker is
-- the safe ceiling; 2 fits only if both workers are I/O-bound (waiting on external
-- API); 3+ starts crowding BLAI. The orchestrator ENFORCES a hard limit of 1
-- concurrent backfill via the 'running' status check + concurrencyPolicy: Forbid
-- on its CronJob.

BEGIN;

CREATE TABLE IF NOT EXISTS meta.backfill_state (
    source_name TEXT PRIMARY KEY,

    -- How to invoke the fetcher
    fetcher_module TEXT NOT NULL DEFAULT 'dk_data.ingestion.main',
    fetcher_args TEXT[] NOT NULL DEFAULT '{}',
    category TEXT NOT NULL,

    -- Soft target: when to consider this source 'complete'
    -- (per github issue #256 expected row counts)
    expected_min_rows BIGINT,
    expected_window_label TEXT,  -- e.g., '15 years', '20 years', '5 CMS years', 'full corpus'

    -- Status state machine
    status TEXT NOT NULL DEFAULT 'paused'
        CHECK (status IN ('paused','active','running','complete','failed','blocked')),
    priority INT NOT NULL DEFAULT 100,  -- lower = higher priority
    consecutive_failures INT NOT NULL DEFAULT 0,
    consecutive_noops INT NOT NULL DEFAULT 0,  -- count of runs that loaded zero new rows

    -- Accounting (rolls up across all chunks)
    chunks_run INT NOT NULL DEFAULT 0,
    total_rows_loaded BIGINT NOT NULL DEFAULT 0,
    total_wal_mb NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_duration_seconds BIGINT NOT NULL DEFAULT 0,

    -- Timing
    activated_at TIMESTAMPTZ,
    last_attempt_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    last_failure_reason TEXT,
    completed_at TIMESTAMPTZ,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS meta_backfill_state_status_idx
    ON meta.backfill_state (status, priority, last_success_at NULLS FIRST);

-- =============================================================================
-- meta.backfill_orchestrator_pick(): pick the next source to chunk
-- =============================================================================
-- Returns one row with the picked source, or zero rows if nothing should run.
-- Atomically marks the picked source as status='running' so concurrent ticks
-- won't double-pick.
-- =============================================================================
CREATE OR REPLACE FUNCTION meta.backfill_orchestrator_pick(
    p_max_active            INT DEFAULT 1,
    p_pg_activity_threshold INT DEFAULT 30,
    p_daily_wal_budget_gb   NUMERIC DEFAULT 50
) RETURNS TABLE (
    source_name    TEXT,
    fetcher_module TEXT,
    fetcher_args   TEXT[],
    category       TEXT
)
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_active_pg_count   INT;
    v_running_count     INT;
    v_today_wal_mb      NUMERIC;
BEGIN
    -- Circuit breaker 1: cluster busy?
    SELECT count(*) INTO v_active_pg_count
    FROM pg_stat_activity
    WHERE datname = current_database()
      AND state = 'active'
      AND pid <> pg_backend_pid();
    IF v_active_pg_count > p_pg_activity_threshold THEN
        RAISE NOTICE 'backfill_orchestrator: skip — pg_stat_activity active=% > %',
            v_active_pg_count, p_pg_activity_threshold;
        RETURN;
    END IF;

    -- Circuit breaker 2: another backfill already running?
    SELECT count(*) INTO v_running_count
    FROM meta.backfill_state
    WHERE status = 'running';
    IF v_running_count >= p_max_active THEN
        RAISE NOTICE 'backfill_orchestrator: skip — % running already', v_running_count;
        RETURN;
    END IF;

    -- Circuit breaker 3: daily WAL budget
    -- (Section 9 budget: < 50 GB/day total)
    SELECT COALESCE(SUM(wal_bytes / 1024.0 / 1024.0), 0) INTO v_today_wal_mb
    FROM meta.wal_usage
    WHERE recorded_at >= date_trunc('day', NOW());
    IF v_today_wal_mb > (p_daily_wal_budget_gb * 1024) THEN
        RAISE NOTICE 'backfill_orchestrator: skip — daily WAL budget exhausted (% MB > % GB)',
            v_today_wal_mb, p_daily_wal_budget_gb;
        RETURN;
    END IF;

    -- Pick: highest priority, oldest last_success_at, exclude failed/blocked
    RETURN QUERY
    UPDATE meta.backfill_state bs
    SET status = 'running',
        last_attempt_at = NOW()
    WHERE bs.source_name = (
        SELECT inner_bs.source_name
        FROM meta.backfill_state inner_bs
        WHERE inner_bs.status = 'active'
          AND inner_bs.consecutive_failures < 3
          AND inner_bs.consecutive_noops < 3
        ORDER BY inner_bs.priority ASC,
                 inner_bs.last_success_at ASC NULLS FIRST,
                 inner_bs.source_name ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING bs.source_name, bs.fetcher_module, bs.fetcher_args, bs.category;
END;
$fn$;

-- =============================================================================
-- meta.backfill_orchestrator_complete(): mark a chunk as successfully completed
-- =============================================================================
CREATE OR REPLACE FUNCTION meta.backfill_orchestrator_complete(
    p_source_name TEXT,
    p_rows_loaded BIGINT,
    p_wal_mb      NUMERIC,
    p_duration_seconds BIGINT
) RETURNS VOID
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_total_after BIGINT;
    v_target      BIGINT;
BEGIN
    UPDATE meta.backfill_state
    SET total_rows_loaded     = total_rows_loaded + p_rows_loaded,
        total_wal_mb          = total_wal_mb + p_wal_mb,
        total_duration_seconds = total_duration_seconds + p_duration_seconds,
        chunks_run            = chunks_run + 1,
        last_success_at       = NOW(),
        consecutive_failures  = 0,
        consecutive_noops     = CASE
            WHEN p_rows_loaded = 0 THEN consecutive_noops + 1
            ELSE 0
        END,
        status                = 'active'
    WHERE source_name = p_source_name
    RETURNING total_rows_loaded, expected_min_rows
      INTO v_total_after, v_target;

    -- Mark complete if either:
    --   - Reached the expected_min_rows target
    --   - Had 3 consecutive no-op chunks (fetcher's checkpoint indicates no more pages)
    UPDATE meta.backfill_state
    SET status = 'complete', completed_at = NOW()
    WHERE source_name = p_source_name
      AND status = 'active'
      AND (
          (v_target IS NOT NULL AND v_total_after >= v_target)
          OR consecutive_noops >= 3
      );
END;
$fn$;

-- =============================================================================
-- meta.backfill_orchestrator_fail(): mark a chunk as failed
-- =============================================================================
CREATE OR REPLACE FUNCTION meta.backfill_orchestrator_fail(
    p_source_name TEXT,
    p_reason      TEXT
) RETURNS VOID
LANGUAGE plpgsql
AS $fn$
BEGIN
    UPDATE meta.backfill_state
    SET consecutive_failures = consecutive_failures + 1,
        last_failure_at      = NOW(),
        last_failure_reason  = p_reason,
        status               = CASE
            WHEN consecutive_failures + 1 >= 3 THEN 'failed'
            ELSE 'active'
        END
    WHERE source_name = p_source_name;
END;
$fn$;

-- =============================================================================
-- meta.backfill_orchestrator_release(): release a stuck 'running' lock
-- =============================================================================
-- Used by the cronjob's trap/cleanup to release the running flag if the script
-- dies unexpectedly. Also called by a separate cleanup cron to time out stuck rows.
CREATE OR REPLACE FUNCTION meta.backfill_orchestrator_release(
    p_source_name TEXT
) RETURNS VOID
LANGUAGE plpgsql
AS $fn$
BEGIN
    UPDATE meta.backfill_state
    SET status = 'active'
    WHERE source_name = p_source_name AND status = 'running';
END;
$fn$;

-- =============================================================================
-- meta.backfill_orchestrator_cleanup_stuck(): release sources stuck in 'running'
-- =============================================================================
-- Called by the orchestrator at the start of every tick. Any source whose
-- last_attempt_at is older than the orchestrator's max runtime is presumed
-- dead and released back to 'active'.
CREATE OR REPLACE FUNCTION meta.backfill_orchestrator_cleanup_stuck(
    p_max_runtime_minutes INT DEFAULT 60
) RETURNS INT
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_count INT;
BEGIN
    UPDATE meta.backfill_state
    SET status = 'active',
        last_failure_reason = format('orphaned running lock — last_attempt_at=%s', last_attempt_at)
    WHERE status = 'running'
      AND last_attempt_at < NOW() - (p_max_runtime_minutes || ' minutes')::interval;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$fn$;

-- =============================================================================
-- View: meta.backfill_progress (human-readable status)
-- =============================================================================
CREATE OR REPLACE VIEW meta.backfill_progress AS
SELECT
    source_name,
    category,
    status,
    priority,
    expected_window_label,
    total_rows_loaded,
    expected_min_rows,
    CASE WHEN expected_min_rows > 0
         THEN ROUND(LEAST(100, total_rows_loaded::numeric * 100 / expected_min_rows), 1)
         ELSE NULL
    END AS percent_complete,
    chunks_run,
    total_wal_mb,
    ROUND(total_duration_seconds::numeric / 60, 1) AS total_minutes,
    consecutive_failures,
    consecutive_noops,
    last_success_at,
    last_failure_at,
    last_failure_reason,
    completed_at
FROM meta.backfill_state
ORDER BY
    CASE status
        WHEN 'failed' THEN 1
        WHEN 'running' THEN 2
        WHEN 'active' THEN 3
        WHEN 'paused' THEN 4
        WHEN 'complete' THEN 5
    END,
    priority ASC,
    source_name ASC;

-- Grant the orchestrator role
DO $$ BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON meta.backfill_state TO mol_data_ops';
        EXECUTE 'GRANT EXECUTE ON FUNCTION meta.backfill_orchestrator_pick(INT, INT, NUMERIC) TO mol_data_ops';
        EXECUTE 'GRANT EXECUTE ON FUNCTION meta.backfill_orchestrator_complete(TEXT, BIGINT, NUMERIC, BIGINT) TO mol_data_ops';
        EXECUTE 'GRANT EXECUTE ON FUNCTION meta.backfill_orchestrator_fail(TEXT, TEXT) TO mol_data_ops';
        EXECUTE 'GRANT EXECUTE ON FUNCTION meta.backfill_orchestrator_release(TEXT) TO mol_data_ops';
        EXECUTE 'GRANT EXECUTE ON FUNCTION meta.backfill_orchestrator_cleanup_stuck(INT) TO mol_data_ops';
        EXECUTE 'GRANT SELECT ON meta.backfill_progress TO mol_data_ops';
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        EXECUTE 'GRANT SELECT ON meta.backfill_state TO analyst';
        EXECUTE 'GRANT SELECT ON meta.backfill_progress TO analyst';
    END IF;
END $$;

-- Per-table autovacuum tuning (matches the pattern in 036a_autovacuum_tuning.sql)
ALTER TABLE meta.backfill_state SET (
    autovacuum_vacuum_scale_factor = 0.1,
    autovacuum_vacuum_threshold = 100,
    autovacuum_analyze_scale_factor = 0.05,
    autovacuum_analyze_threshold = 50
);

COMMIT;
