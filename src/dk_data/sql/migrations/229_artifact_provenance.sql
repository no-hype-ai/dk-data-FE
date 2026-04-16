-- Feature: Horizon 2 / plan §C.4 — download integrity pipeline
--
-- Durable provenance store for every downloaded artifact: one row per
-- (source, url, download). Captures the upstream HTTP headers that govern
-- change-detection (Content-Length, ETag, Last-Modified), the computed
-- sha256 of the bytes we actually wrote, and the bytes_written we observed
-- on disk — so `size_match = (Content-Length IS NULL OR = bytes_written)`
-- is recomputable server-side without the header.
--
-- Each row optionally points at its prior row for the same (source_name,
-- source_url) pair, and flags `changed_from_prior = TRUE` iff the sha256
-- differs. Ingestion emits two counters wired to this table:
--
--   * dk_artifact_size_mismatch_total{source}  — header said N bytes,
--     disk shows M bytes (already defined; now has a durable backing
--     store via this migration). Incremented in cms_downloader.
--   * dk_artifact_changed_total{source}        — sha256 differs from the
--     most recent prior row for the same (source_name, source_url).
--     Signal for downstream rebuilds (silver transform must re-run even
--     if row-counts match).
--
-- Why a standalone schema: `meta` is the designated home for ingestion
-- orchestration state per CLAUDE.md (meta.job_locks, meta.transform_runs,
-- meta.backfill_state, meta.wal_usage). Provenance is exactly that shape.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS so
-- the migration is safe to rerun against an already-initialised database
-- (see plan §C.4 hard constraint).

BEGIN;

CREATE TABLE IF NOT EXISTS meta.artifact_provenance (
    provenance_id       BIGSERIAL   PRIMARY KEY,
    source_name         TEXT        NOT NULL,
    source_url          TEXT        NOT NULL,
    local_path          TEXT        NOT NULL,
    content_length      BIGINT,
    etag                TEXT,
    last_modified       TEXT,           -- HTTP header, keep as string to avoid timezone-parse surprises
    sha256              TEXT        NOT NULL,
    bytes_written       BIGINT      NOT NULL,
    size_match          BOOLEAN     NOT NULL,
    downloaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    prior_provenance_id BIGINT      REFERENCES meta.artifact_provenance(provenance_id),
    changed_from_prior  BOOLEAN     NOT NULL DEFAULT FALSE
);

-- Lookup path for the "most recent row for this (source, url)" query that
-- runs on every download — needs to be the first access. DESC on
-- downloaded_at so LIMIT 1 reads the first tuple from the index.
CREATE INDEX IF NOT EXISTS artifact_provenance_source_downloaded_idx
    ON meta.artifact_provenance (source_name, downloaded_at DESC);

COMMIT;
