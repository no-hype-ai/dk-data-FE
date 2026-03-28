-- Migration: 085_who_icd_catalog_and_dedup
-- Feature: 015-assessment-dashboard-integration
-- Purpose: Add deduplication constraint on raw.who_icd.request_id and
--          register the who_icd source in meta.data_sources.
-- Depends on: 075_pdb_who_raw_tables.sql, 083_meta_data_sources_create.sql

BEGIN;

-- =============================================================================
-- raw.who_icd — add unique constraint on request_id for ON CONFLICT DO NOTHING
-- =============================================================================
-- request_id encodes "who_icd:<icd_code>" which provides per-code dedup.
-- We also add a unique index on response_body_hash so identical responses
-- (same code, same content) are not inserted twice across runs.

DO $$
BEGIN
    -- Guard: table may not exist if migration 075 was not run (e.g., partial setups)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'raw' AND table_name = 'who_icd'
    ) THEN
        RETURN;
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema   = 'raw'
          AND table_name     = 'who_icd'
          AND constraint_name = 'uidx_raw_who_icd_request_id'
    ) THEN
        ALTER TABLE raw.who_icd
            ADD CONSTRAINT uidx_raw_who_icd_request_id UNIQUE (request_id);
    END IF;
END
$$;

DO $$
BEGIN
    -- Guard: table may not exist if migration 075 was not run
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'raw' AND table_name = 'who_icd'
    ) THEN
        RETURN;
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'raw'
          AND tablename  = 'who_icd'
          AND indexname  = 'uidx_raw_who_icd_body_hash'
    ) THEN
        CREATE UNIQUE INDEX uidx_raw_who_icd_body_hash
            ON raw.who_icd (response_body_hash)
            WHERE response_body_hash IS NOT NULL;
    END IF;
END
$$;

-- =============================================================================
-- meta.data_sources — register who_icd (journal_rss and medical_news already
-- seeded by migration 083, but who_icd was missing)
-- meta.data_sources columns: source_name, source_type, description,
--   refresh_frequency, is_active (others are auto or optional)
-- =============================================================================

INSERT INTO meta.data_sources (source_name, source_type, description, refresh_frequency, is_active)
VALUES (
    'who_icd',
    'api',
    'WHO ICD-11 disease classification codes (with ICD-10 fallback via public API)',
    'monthly',
    TRUE
)
ON CONFLICT (source_name) DO UPDATE SET
    description       = EXCLUDED.description,
    refresh_frequency = EXCLUDED.refresh_frequency,
    is_active         = EXCLUDED.is_active;

COMMIT;

DO $$
BEGIN
    RAISE NOTICE 'Migration 085_who_icd_catalog_and_dedup complete.';
    RAISE NOTICE 'Added UNIQUE constraint on raw.who_icd.request_id';
    RAISE NOTICE 'Registered who_icd in meta.data_sources';
END $$;
