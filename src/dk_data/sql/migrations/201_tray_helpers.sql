-- Migration 031/029: Generic tray-pattern helpers
-- Feature: 001-silver-medallion-rebuild (audit fix 2026-04-12)
--
-- The tray pattern (transformation-reliability-low-tech-solutions.md Section 4)
-- has substantial boilerplate that repeats across every heavy bronze table:
--   - acquire job lock with TTL
--   - snapshot non-essential indexes
--   - create UNLOGGED tray
--   - SET LOGGED
--   - drop old indexes
--   - atomic swap
--   - drop old table
--   - recreate indexes CONCURRENTLY
--   - release lock
--
-- Each table-specific tray procedure should call _tray_setup() at the start,
-- run its own chunked transformation INSERT into the tray, then call
-- _tray_finalize() at the end. This factors ~80 lines of boilerplate into
-- two helper procedures, leaving each tray procedure to focus on the
-- table-specific transformation.

BEGIN;

CREATE TABLE IF NOT EXISTS meta.tray_index_snapshots (
    proc_name   TEXT NOT NULL,
    index_name  TEXT NOT NULL,
    index_def   TEXT NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (proc_name, index_name)
);

-- ============================================================================
-- _tray_setup: acquire lock, snapshot indexes, create UNLOGGED tray
-- ============================================================================
CREATE OR REPLACE PROCEDURE mol_bronze._tray_setup(
    p_proc_name TEXT,
    p_schema    TEXT,
    p_target    TEXT,
    p_tray      TEXT,
    p_lock_hours INT DEFAULT 6
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Acquire job lock with TTL (PgBouncer-safe persistent lock)
    DELETE FROM meta.job_locks WHERE name = p_proc_name AND expires_at < NOW();
    INSERT INTO meta.job_locks (name, locked_by, locked_at, expires_at)
    VALUES (p_proc_name, pg_backend_pid()::text, NOW(),
            NOW() + (p_lock_hours || ' hours')::interval)
    ON CONFLICT (name) DO NOTHING;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Could not acquire job lock for %; another instance may be running', p_proc_name;
    END IF;

    -- Snapshot non-essential indexes (everything except PK / UNIQUE constraints)
    DELETE FROM meta.tray_index_snapshots WHERE proc_name = p_proc_name;
    EXECUTE format(
        $sql$
        INSERT INTO meta.tray_index_snapshots (proc_name, index_name, index_def)
        SELECT %L, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = %L AND tablename = %L
          AND indexname NOT IN (
              SELECT conname FROM pg_constraint
              WHERE conrelid = (%L || '.' || %L)::regclass
                AND contype IN ('p', 'u')
          )
        $sql$,
        p_proc_name, p_schema, p_target, p_schema, p_target
    );

    -- Create UNLOGGED tray with no indexes (zero index churn during chunked load)
    EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', p_schema, p_tray);
    EXECUTE format(
        'CREATE UNLOGGED TABLE %I.%I (LIKE %I.%I INCLUDING DEFAULTS INCLUDING CONSTRAINTS)',
        p_schema, p_tray, p_schema, p_target
    );
END;
$$;

-- ============================================================================
-- _tray_finalize: SET LOGGED, drop old indexes, atomic swap, drop old, recreate indexes
-- ============================================================================
CREATE OR REPLACE PROCEDURE mol_bronze._tray_finalize(
    p_proc_name TEXT,
    p_schema    TEXT,
    p_target    TEXT,
    p_tray      TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_old_name  TEXT := p_target || '_old';
    v_index_name TEXT;
    v_index_def  TEXT;
    v_total_wal_bytes BIGINT;
    v_total_wal_mb    NUMERIC;
    v_total_rows      BIGINT;
BEGIN
    -- 1. SET LOGGED on the tray (single bulk WAL write for the data; no indexes yet)
    EXECUTE format('ALTER TABLE %I.%I SET LOGGED', p_schema, p_tray);
    COMMIT;

    -- 2. Drop the snapshotted non-essential indexes from the bronze target
    FOR v_index_name IN
        SELECT index_name FROM meta.tray_index_snapshots WHERE proc_name = p_proc_name
    LOOP
        EXECUTE format('DROP INDEX IF EXISTS %I.%I', p_schema, v_index_name);
    END LOOP;
    COMMIT;

    -- 3. Atomic swap (target → old, tray → target)
    EXECUTE format('ALTER TABLE %I.%I RENAME TO %I', p_schema, p_target, v_old_name);
    EXECUTE format('ALTER TABLE %I.%I RENAME TO %I', p_schema, p_tray, p_target);
    COMMIT;

    -- 4. Drop the orphaned old table
    EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', p_schema, v_old_name);
    COMMIT;

    -- 5. Recreate non-essential indexes CONCURRENTLY on the new target
    -- (queries against the new bronze table work even before they finish)
    FOR v_index_def IN
        SELECT REPLACE(index_def, 'CREATE INDEX ', 'CREATE INDEX CONCURRENTLY IF NOT EXISTS ')
        FROM meta.tray_index_snapshots WHERE proc_name = p_proc_name
    LOOP
        BEGIN
            EXECUTE v_index_def;
        EXCEPTION WHEN duplicate_table OR duplicate_object THEN
            -- Index name already exists (rare race during reapply); ignore
            NULL;
        END;
    END LOOP;

    -- 6. Emit a structured log line that the dk-data-wal-explosion alert matches.
    -- The Loki alert in grafana/alerts/dk-data.yaml fires when wal_mb > 5000.
    SELECT COALESCE(SUM(wal_bytes), 0), COALESCE(SUM(rows_processed), 0)
      INTO v_total_wal_bytes, v_total_rows
    FROM meta.transform_runs WHERE procedure_name = p_proc_name;
    v_total_wal_mb := ROUND(v_total_wal_bytes::numeric / 1024.0 / 1024.0, 2);
    RAISE NOTICE 'tray_finalize procedure=% wal_mb=% rows=%',
        p_proc_name, v_total_wal_mb, v_total_rows;

    -- Also persist to meta.wal_usage so the Mimir-side dashboards can graph it
    INSERT INTO meta.wal_usage (job_name, wal_mb, logged_at)
    VALUES (p_proc_name, v_total_wal_mb, NOW());

    -- 7. Release the lock
    DELETE FROM meta.job_locks WHERE name = p_proc_name;
    COMMIT;
END;
$$;

COMMIT;
