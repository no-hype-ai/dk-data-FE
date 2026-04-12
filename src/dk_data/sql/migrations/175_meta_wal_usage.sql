-- WAL usage tracking table
-- Feature: 001-silver-medallion-rebuild / T221
-- Records WAL bytes consumed per transform chunk for budget enforcement.
-- Populated by measure_wal() context manager (T226).
-- FR-021: max 2 GiB WAL per transform chunk.

CREATE TABLE IF NOT EXISTS meta.wal_usage (
    id              bigserial PRIMARY KEY,
    recorded_at     timestamptz NOT NULL DEFAULT now(),
    procedure_name  text NOT NULL,
    chunk_index     int  NOT NULL DEFAULT 0,
    wal_bytes       bigint NOT NULL,
    rows_processed  bigint,
    duration_ms     numeric(12,3),
    pod_name        text,
    exceeded_limit  boolean NOT NULL DEFAULT false,  -- true if > 2 GiB
    CONSTRAINT wal_usage_bytes_positive CHECK (wal_bytes >= 0)
);

CREATE INDEX IF NOT EXISTS wal_usage_recorded_at_brin
    ON meta.wal_usage USING BRIN (recorded_at);

CREATE INDEX IF NOT EXISTS wal_usage_procedure
    ON meta.wal_usage (procedure_name, recorded_at DESC);

COMMENT ON TABLE meta.wal_usage IS
    'WAL bytes consumed per transform chunk. FR-021 ceiling: 2 GiB. Populated by measure_wal() in dk_data.ingestion.utils.wal_metrics.';

COMMENT ON COLUMN meta.wal_usage.exceeded_limit IS
    'Set true when wal_bytes > 2147483648 (2 GiB). Used by T098 alert rule.';

-- View for monitoring: recent chunks that breached the 2 GiB ceiling
CREATE OR REPLACE VIEW meta.wal_usage_alerts AS
SELECT
    recorded_at,
    procedure_name,
    chunk_index,
    wal_bytes,
    round(wal_bytes / 1073741824.0, 3) AS wal_gib,
    rows_processed,
    duration_ms,
    pod_name
FROM meta.wal_usage
WHERE exceeded_limit = true
ORDER BY recorded_at DESC;
