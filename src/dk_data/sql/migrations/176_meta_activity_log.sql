-- Activity log snapshot table
-- Feature: 001-silver-medallion-rebuild / T222
-- Periodic snapshots of pg_stat_activity for offline analysis of
-- connection and lock contention patterns.

CREATE TABLE IF NOT EXISTS meta.activity_log (
    id              bigserial PRIMARY KEY,
    snapshotted_at  timestamptz NOT NULL DEFAULT now(),
    pid             int,
    usename         text,
    application_name text,
    client_addr     inet,
    state           text,
    wait_event_type text,
    wait_event      text,
    query_duration_ms numeric(12,3),
    query_prefix    text,           -- first 200 chars (no full query stored)
    backend_type    text
);

CREATE INDEX IF NOT EXISTS activity_log_snapshotted_at_brin
    ON meta.activity_log USING BRIN (snapshotted_at);

COMMENT ON TABLE meta.activity_log IS
    'Periodic snapshots of pg_stat_activity. Captured by cronjob-activity-log-snapshot (T228).';

-- Snapshot function — called by the CronJob
CREATE OR REPLACE FUNCTION meta.snapshot_activity()
RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
    inserted int;
BEGIN
    INSERT INTO meta.activity_log (
        snapshotted_at,
        pid,
        usename,
        application_name,
        client_addr,
        state,
        wait_event_type,
        wait_event,
        query_duration_ms,
        query_prefix,
        backend_type
    )
    SELECT
        now(),
        pid,
        usename,
        application_name,
        client_addr,
        state,
        wait_event_type,
        wait_event,
        EXTRACT(EPOCH FROM (now() - query_start)) * 1000,
        left(query, 200),
        backend_type
    FROM pg_stat_activity
    WHERE pid <> pg_backend_pid();

    GET DIAGNOSTICS inserted = ROW_COUNT;
    RETURN inserted;
END;
$$;

-- Retention: purge snapshots older than 7 days
CREATE OR REPLACE FUNCTION meta.purge_activity_log(p_days int DEFAULT 7)
RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
    deleted int;
BEGIN
    DELETE FROM meta.activity_log
    WHERE snapshotted_at < now() - (p_days || ' days')::interval;
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$;
