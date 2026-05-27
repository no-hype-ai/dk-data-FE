-- Migration 074: Fix schema drift from issue #189
--
-- S1: meta.refresh_log column name mismatch
--     Code writes refresh_started_at / refresh_completed_at.
--     Older Docker dev environments may have been initialised with
--     started_at / completed_at (pre-migration column names).
--     This migration renames the columns to match the code, but only
--     if the old names still exist (idempotent via DO $$ block).
--
-- S2: mol_raw.pubchem missing UNIQUE constraint on request_id
--     The loader uses ON CONFLICT (request_id) DO NOTHING.
--     Without the constraint, every insert raises:
--     "there is no unique or exclusion constraint matching the
--      ON CONFLICT specification"

-- S1: Rename meta.refresh_log columns if they have old names ----------------

DO $$
BEGIN
    -- Rename started_at → refresh_started_at if old column still exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'meta'
          AND table_name   = 'refresh_log'
          AND column_name  = 'started_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'meta'
          AND table_name   = 'refresh_log'
          AND column_name  = 'refresh_started_at'
    ) THEN
        ALTER TABLE meta.refresh_log
            RENAME COLUMN started_at TO refresh_started_at;
        RAISE NOTICE 'Renamed meta.refresh_log.started_at → refresh_started_at';
    ELSE
        RAISE NOTICE 'meta.refresh_log.refresh_started_at already correct — skipping';
    END IF;

    -- Rename completed_at → refresh_completed_at if old column still exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'meta'
          AND table_name   = 'refresh_log'
          AND column_name  = 'completed_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'meta'
          AND table_name   = 'refresh_log'
          AND column_name  = 'refresh_completed_at'
    ) THEN
        ALTER TABLE meta.refresh_log
            RENAME COLUMN completed_at TO refresh_completed_at;
        RAISE NOTICE 'Renamed meta.refresh_log.completed_at → refresh_completed_at';
    ELSE
        RAISE NOTICE 'meta.refresh_log.refresh_completed_at already correct — skipping';
    END IF;
END $$;

-- S2: Add UNIQUE constraint on mol_raw.pubchem(request_id) -----------------
-- Matches the ON CONFLICT (request_id) clause used by the loader.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'mol_raw'
          AND tablename  = 'pubchem'
          AND indexname  = 'uq_mol_raw_pubchem_request_id'
    ) THEN
        ALTER TABLE mol_raw.pubchem
            ADD CONSTRAINT uq_mol_raw_pubchem_request_id UNIQUE (request_id);
        RAISE NOTICE 'Added UNIQUE constraint on mol_raw.pubchem(request_id)';
    ELSE
        RAISE NOTICE 'UNIQUE constraint on mol_raw.pubchem(request_id) already exists — skipping';
    END IF;
END $$;
