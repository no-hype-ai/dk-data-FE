-- Migration: 003a_meta_transform_runs.sql
-- Feature: 001-silver-medallion-rebuild
-- FR-021 (research Topic 5): meta.transform_runs — per-chunk WAL accounting.
--
-- Each chunked bootstrap procedure calls pg_current_wal_lsn() at chunk start
-- and end, computes the byte delta with pg_wal_lsn_diff(), and inserts a row
-- here.  This is the application-side substitute for pg_stat_statements (which
-- is disabled on this cluster).
--
-- The prometheus exporter (T097) emits:
--   dk_data_transform_chunk_wal_bytes{procedure_name, chunk_position}
--   dk_data_transform_chunk_rows{procedure_name, chunk_position}
--
-- The Grafana alert fires when wal_bytes > 2e9 (FR-021 ceiling per chunk).

BEGIN;

CREATE TABLE IF NOT EXISTS meta.transform_runs (
    run_id         bigserial    PRIMARY KEY,
    procedure_name text         NOT NULL,
    chunk_position text         NOT NULL,
    started_at     timestamptz  NOT NULL,
    ended_at       timestamptz  NOT NULL,
    rows_processed bigint       NOT NULL,
    wal_bytes      bigint       NOT NULL
);

CREATE INDEX IF NOT EXISTS meta_transform_runs_procedure_started_idx
    ON meta.transform_runs (procedure_name, started_at);

-- Alert index: only index chunks that already exceeded the 500 MB advisory limit
-- (so the index stays small under normal operations).
CREATE INDEX IF NOT EXISTS meta_transform_runs_wal_bytes_large_idx
    ON meta.transform_runs (wal_bytes)
    WHERE wal_bytes > 500000000;

COMMENT ON TABLE meta.transform_runs IS
    'FR-021 / research Topic 5: per-chunk WAL accounting for bootstrap procedures. '
    'Populated by each PL/pgSQL procedure after every committed chunk. '
    'The 2 GB hard ceiling per chunk is enforced via the Grafana alert on wal_bytes > 2e9.';

COMMENT ON COLUMN meta.transform_runs.chunk_position IS
    'Opaque progress cursor matching meta.refresh_state.last_chunk_position '
    'for the same procedure run.';
COMMENT ON COLUMN meta.transform_runs.wal_bytes IS
    'pg_wal_lsn_diff(end_lsn, start_lsn) for this chunk. '
    'Alert fires when this exceeds 500 MB; hard ceiling is 2 GB (FR-021).';

COMMIT;
