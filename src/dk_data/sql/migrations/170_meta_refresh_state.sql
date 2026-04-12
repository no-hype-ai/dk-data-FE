-- Migration: 002_meta_refresh_state.sql
-- Feature: 001-silver-medallion-rebuild
-- FR-026: meta.refresh_state — per-procedure resumability checkpoint.
--
-- Every chunked PL/pgSQL bootstrap procedure records its last committed
-- chunk_position here so a mid-run kill can be resumed from the last checkpoint.
--
-- Procedure usage pattern:
--   INSERT INTO meta.refresh_state (procedure_name, last_chunk_position, status)
--     VALUES ('bootstrap_providers', '0', 'in_progress')
--     ON CONFLICT (procedure_name) DO UPDATE
--       SET last_chunk_position = EXCLUDED.last_chunk_position,
--           last_commit_at = NOW(),
--           status = 'in_progress';
--
-- On restart, the procedure reads last_chunk_position and skips already-committed rows.

BEGIN;

CREATE TABLE IF NOT EXISTS meta.refresh_state (
    procedure_name       text        PRIMARY KEY,
    last_chunk_position  text        NOT NULL,
    last_commit_at       timestamptz DEFAULT NOW(),
    status               text        DEFAULT 'in_progress'
        CHECK (status IN ('in_progress', 'completed', 'failed'))
);

COMMENT ON TABLE meta.refresh_state IS
    'FR-026: per-procedure resumability checkpoint. Each chunked bootstrap '
    'procedure upserts its progress here after each committed chunk.';

COMMENT ON COLUMN meta.refresh_state.last_chunk_position IS
    'Opaque progress cursor — typically the last processed primary key or offset. '
    'Procedure-specific; must be comparable with >= or > to resume from the right row.';
COMMENT ON COLUMN meta.refresh_state.status IS
    'Lifecycle: in_progress → completed (procedure finishes); '
    'in_progress → failed (procedure errors); completed → in_progress (next refresh).';

COMMIT;
