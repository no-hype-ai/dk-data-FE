-- Slow query log table
-- Feature: 001-silver-medallion-rebuild / T220
-- Records queries that exceed a configurable duration threshold.
-- Populated by the application-side timed_query() context manager (T224).

CREATE TABLE IF NOT EXISTS meta.slow_query_log (
    id              bigserial PRIMARY KEY,
    logged_at       timestamptz NOT NULL DEFAULT now(),
    duration_ms     numeric(12,3) NOT NULL,
    query_hash      text,           -- md5 of query text (no PII)
    query_prefix    text,           -- first 200 chars for debugging
    schema_name     text,
    table_name      text,
    operation       text,           -- SELECT, INSERT, UPDATE, DELETE
    pod_name        text,
    service_name    text,
    CONSTRAINT slow_query_duration_positive CHECK (duration_ms > 0)
);

CREATE INDEX IF NOT EXISTS slow_query_log_logged_at_brin
    ON meta.slow_query_log USING BRIN (logged_at);

CREATE INDEX IF NOT EXISTS slow_query_log_schema_table
    ON meta.slow_query_log (schema_name, table_name);

COMMENT ON TABLE meta.slow_query_log IS
    'Application-side slow query log. Threshold: 5000ms. Populated by timed_query() in dk_data.ingestion.utils.db_timing.';

-- Retention: delete rows older than 30 days to keep table bounded
-- Executed by the activity-log-snapshot CronJob (T228).
CREATE OR REPLACE FUNCTION meta.purge_slow_query_log(p_days int DEFAULT 30)
RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
    deleted int;
BEGIN
    DELETE FROM meta.slow_query_log
    WHERE logged_at < now() - (p_days || ' days')::interval;
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$;
