-- 099_fetch_state_table.sql
-- Persistent fetch state for all ingestion fetchers.
--
-- Replaces the file-based manifest system (.manifests/<source>.json) with
-- a PostgreSQL-backed store so that ETag, cursor, offset, and content-hash
-- state survives Kubernetes pod restarts between CronJob runs.
--
-- BaseFetcher.load_manifest() / save_manifest() write here first;
-- the file-based fallback is kept for local dev without a DB connection.

CREATE TABLE IF NOT EXISTS raw.fetch_state (
    source_name  VARCHAR(100) PRIMARY KEY,
    manifest     JSONB        NOT NULL DEFAULT '{}',
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE raw.fetch_state IS
    'Per-source fetch state persisted between Kubernetes CronJob runs. '
    'Stores ETag, Last-Modified, cursor, offset, content hash, and run status.';

COMMENT ON COLUMN raw.fetch_state.source_name IS
    'Matches BaseFetcher.SOURCE_NAME (e.g. ''pubmed'', ''uniprot'').';

COMMENT ON COLUMN raw.fetch_state.manifest IS
    'JSON object with fields: last_run_at, last_run_status, total_records_fetched, '
    'last_content_hash, etag, last_modified, last_cursor, last_offset, saved_at.';
