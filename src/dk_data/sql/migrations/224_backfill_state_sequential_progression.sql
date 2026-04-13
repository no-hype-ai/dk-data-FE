-- Migration: 224_backfill_state_sequential_progression
-- Feature: 002-external-integration-foundation (US-20, T152a/T152b)
-- Purpose: Add `last_year_processed` and `last_range_processed` columns
--          to `meta.backfill_state` so the consolidated chembl and
--          pubchem cronjobs (T127a, T127d) can advance sequentially
--          through years / CID ranges without a second state table.
--
-- Why this is separate from migration 220: migration 220 touches
-- `source_name` rows only (alignment). Adding columns is a schema
-- change that deserves its own migration file so rollback is cleaner.
--
-- Column semantics:
--   - `last_year_processed` INT NULL — chembl: YYYY of the most recent
--     fully-backfilled year. NULL on first run.
--   - `last_range_processed` INT NULL — pubchem: 1..6 of the most
--     recent fully-backfilled CID range. NULL on first run.
--   - Both are NULL for every other source. The loaders ignore them
--     unless they're explicitly set.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS.
--
-- Run: psql ... -f migrations/224_backfill_state_sequential_progression.sql

BEGIN;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '10s';

-- Guard: table must exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'meta' AND table_name = 'backfill_state'
    ) THEN
        RAISE EXCEPTION 'meta.backfill_state does not exist — run migration 165 first';
    END IF;
END $$;

ALTER TABLE meta.backfill_state
    ADD COLUMN IF NOT EXISTS last_year_processed INT,
    ADD COLUMN IF NOT EXISTS last_range_processed INT;

COMMENT ON COLUMN meta.backfill_state.last_year_processed IS
    'Sequential progression checkpoint for per-year backfill (e.g. chembl_activities 2010–2026). NULL means the source has not run yet; 2026 means the source has completed its historical backfill and is in steady-state mode. Updated by the per-source cronjob on every successful tick.';

COMMENT ON COLUMN meta.backfill_state.last_range_processed IS
    'Sequential progression checkpoint for per-range backfill (e.g. pubchem_molecules ranges 1–6). NULL means the source has not run yet; N means range N has been fully fetched. Updated by the per-source cronjob on every successful tick.';

DO $$
BEGIN
    RAISE NOTICE '224_backfill_state_sequential_progression complete';
    RAISE NOTICE 'Added columns: last_year_processed, last_range_processed';
END $$;

COMMIT;
