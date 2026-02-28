-- 082: Audit log retention & archival strategy
--
-- REGULATORY CONTEXT (FDA 21 CFR Part 11, ICH E6(R3), EMA GMP Annex 11):
--   Audit trails must be retained for at least as long as the associated
--   electronic records. For GxP pharmaceutical systems this means:
--     - Clinical trial records: min 2 years post-approval (FDA), up to 25 years (ICH/EU)
--     - Manufacturing records: 1-3 years after batch expiration (21 CFR 211.180)
--     - AI provenance logs: same as the GxP records they support
--
--   CRITICAL: Audit logs must NOT be deleted during the retention period.
--   Uncontrolled deletion of electronic data is a top data integrity finding.
--
-- STRATEGY: Tier the data — keep hot data in the main table, archive old
-- data to a partitioned cold table. NEVER hard-delete within retention.
--
--   Hot tier  (meta.api_audit_log):      last 365 days — fast queries
--   Cold tier (meta.api_audit_log_archive): 1-7 years — compressed, queryable
--   Purge:    only records older than 7 years (2555 days) may be purged
--             (configurable — set higher for GCP/ICH compliance)

BEGIN;

-- ─── Cold archive table (same schema, partitioned by year) ──────────────────
CREATE TABLE IF NOT EXISTS meta.api_audit_log_archive (
    id              BIGINT          NOT NULL,
    request_id      UUID            NOT NULL,
    timestamp       TIMESTAMPTZ     NOT NULL,
    source          VARCHAR(20)     NOT NULL DEFAULT 'job-trigger',
    method          VARCHAR(10),
    path            TEXT,
    query_params    JSONB,
    user_role       VARCHAR(50),
    user_sub        VARCHAR(255),
    ip_address      INET,
    user_agent      TEXT,
    status_code     SMALLINT,
    response_time_ms INTEGER,
    action          VARCHAR(50),
    category        VARCHAR(20),
    details         JSONB,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    archived_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_archive_timestamp
    ON meta.api_audit_log_archive USING BRIN (timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_archive_request_id
    ON meta.api_audit_log_archive (request_id);

-- ─── Archive function (moves old hot data to cold tier) ─────────────────────
CREATE OR REPLACE FUNCTION meta.archive_old_audit_logs(hot_retention_days INT DEFAULT 365)
RETURNS BIGINT AS $$
DECLARE
    archived BIGINT;
BEGIN
    -- Move rows older than hot_retention_days from hot → cold
    WITH moved AS (
        DELETE FROM meta.api_audit_log
        WHERE timestamp < NOW() - (hot_retention_days || ' days')::INTERVAL
        RETURNING *
    )
    INSERT INTO meta.api_audit_log_archive
        (id, request_id, timestamp, source, method, path, query_params,
         user_role, user_sub, ip_address, user_agent, status_code,
         response_time_ms, action, category, details, created_at, archived_at)
    SELECT id, request_id, timestamp, source, method, path, query_params,
           user_role, user_sub, ip_address, user_agent, status_code,
           response_time_ms, action, category, details, created_at, NOW()
    FROM moved;

    GET DIAGNOSTICS archived = ROW_COUNT;

    IF archived > 0 THEN
        RAISE NOTICE 'Archived % audit log rows older than % days', archived, hot_retention_days;
    END IF;

    RETURN archived;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ─── Purge function (ONLY for records past regulatory retention) ────────────
-- Default 2555 days (7 years). For ICH/EU GCP compliance set to 9125 (25 years).
-- This is the ONLY function that permanently deletes audit data.
CREATE OR REPLACE FUNCTION meta.purge_expired_audit_archives(
    max_retention_days INT DEFAULT 2555  -- 7 years
)
RETURNS BIGINT AS $$
DECLARE
    deleted BIGINT;
BEGIN
    -- Safety: refuse to purge anything less than 2 years old
    IF max_retention_days < 730 THEN
        RAISE EXCEPTION 'Retention period must be >= 730 days (2 years) per 21 CFR Part 11';
    END IF;

    DELETE FROM meta.api_audit_log_archive
    WHERE timestamp < NOW() - (max_retention_days || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted = ROW_COUNT;

    IF deleted > 0 THEN
        RAISE NOTICE 'Purged % archived audit log rows older than % days', deleted, max_retention_days;
    END IF;

    RETURN deleted;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ─── Drop the old non-compliant purge function ─────────────────────────────
DROP FUNCTION IF EXISTS meta.purge_old_audit_logs(INT);

-- ─── Grants ─────────────────────────────────────────────────────────────────
GRANT EXECUTE ON FUNCTION meta.archive_old_audit_logs(INT) TO dk_app;
GRANT EXECUTE ON FUNCTION meta.purge_expired_audit_archives(INT) TO dk_app;
GRANT INSERT, SELECT ON meta.api_audit_log_archive TO dk_app;
GRANT SELECT ON meta.api_audit_log_archive TO web_anon;

-- ─── Scheduled via pg_cron (if available) ───────────────────────────────────
DO $cron$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        -- Weekly: archive hot rows older than 365 days
        PERFORM cron.unschedule('purge_audit_logs');  -- remove old job if exists
        PERFORM cron.schedule(
            'archive_audit_logs',
            '0 3 * * 0',  -- Sunday 03:00 UTC
            $$SELECT meta.archive_old_audit_logs(365)$$
        );
        -- Monthly: purge archived rows older than 7 years
        PERFORM cron.schedule(
            'purge_expired_audits',
            '0 4 1 * *',  -- 1st of month 04:00 UTC
            $$SELECT meta.purge_expired_audit_archives(2555)$$
        );
        RAISE NOTICE 'pg_cron: archive weekly (365d hot), purge monthly (7yr retention)';
    ELSE
        RAISE NOTICE 'pg_cron not available — call meta.archive_old_audit_logs(365) from app scheduler';
    END IF;
END $cron$;

-- ─── BRIN index for efficient range scans on the hot table ──────────────────
CREATE INDEX IF NOT EXISTS idx_api_audit_timestamp_brin
    ON meta.api_audit_log USING BRIN (timestamp);

COMMIT;
