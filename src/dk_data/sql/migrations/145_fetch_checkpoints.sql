-- Migration 145: Persistent fetch checkpoint table
-- Feature: 026-fetcher-checkpoint-resume
--
-- Stores per-source pagination/offset state so long-running fetchers
-- (ChEMBL ~2.4M, BindingDB ~3M+) can resume from where they left off
-- after a pod restart, OOMKill, or timeout rather than re-fetching
-- everything from offset 0.
--
-- Design:
--   - One row per source_name (UPSERT pattern)
--   - checkpoint_data is free-form JSONB so each fetcher can store whatever
--     cursor/offset structure it needs (e.g. {"offset": 1500000, "total": 2400000})
--   - cleared automatically on successful run completion
--   - expires after 7 days so stale checkpoints from abandoned runs don't
--     cause incorrect resumes (e.g. after a schema migration or full refresh)

CREATE TABLE IF NOT EXISTS meta.fetch_checkpoints (
    source_name       TEXT        NOT NULL PRIMARY KEY,
    checkpoint_data   JSONB       NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at        TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days'
);

COMMENT ON TABLE meta.fetch_checkpoints IS
    'Persistent per-source pagination checkpoints for resumable long-running fetchers.';

COMMENT ON COLUMN meta.fetch_checkpoints.checkpoint_data IS
    'Free-form JSONB cursor state, e.g. {"offset": 1500000, "total": 2400000} for ChEMBL, '
    '{"records_processed": 1800000} for BindingDB.';

COMMENT ON COLUMN meta.fetch_checkpoints.expires_at IS
    'Checkpoint is ignored and cleared after this timestamp (default 7 days). '
    'Prevents stale state after full-refresh or schema changes.';

-- Index for expired checkpoint cleanup
CREATE INDEX IF NOT EXISTS idx_fetch_checkpoints_expires_at
    ON meta.fetch_checkpoints (expires_at);
