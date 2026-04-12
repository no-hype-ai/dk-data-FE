-- Migration 162: Ensure mol_raw.europepmc and mol_raw.nih_reporter have complete schemas
-- Both bronze models reference these raw tables. Migration 086 created them as *_raw suffix
-- tables, migration 114 renamed them to drop the suffix. Migration 136 may have created
-- them with a minimal schema (no ingested_at). This migration ensures all required columns
-- and indexes exist regardless of which prior migration created the table.

BEGIN;

-- ============================================================================
-- mol_raw.europepmc
-- ============================================================================
CREATE TABLE IF NOT EXISTS mol_raw.europepmc (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        TEXT,
    api_version         TEXT,
    request_params      JSONB,
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    response_size_bytes INTEGER,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           TEXT,
    UNIQUE (request_id)
);

-- Add columns that may be missing if the table was created by an earlier migration
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='mol_raw' AND table_name='europepmc' AND column_name='ingested_at') THEN
        ALTER TABLE mol_raw.europepmc ADD COLUMN ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='mol_raw' AND table_name='europepmc' AND column_name='_loaded_at') THEN
        ALTER TABLE mol_raw.europepmc ADD COLUMN _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_mol_raw_europepmc_processed ON mol_raw.europepmc (processed_to_bronze);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_raw' AND table_name='europepmc' AND column_name='_loaded_at') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_mol_raw_europepmc_loaded ON mol_raw.europepmc (_loaded_at)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_mol_raw_europepmc_loaded_brin
                 ON mol_raw.europepmc USING BRIN (_loaded_at) WITH (pages_per_range = 128)';
    END IF;
END $$;

-- ============================================================================
-- mol_raw.nih_reporter
-- ============================================================================
CREATE TABLE IF NOT EXISTS mol_raw.nih_reporter (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          TEXT NOT NULL,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint        TEXT,
    api_version         TEXT,
    request_params      JSONB,
    response_status     INTEGER,
    response_body       JSONB NOT NULL,
    response_body_hash  TEXT,
    response_size_bytes INTEGER,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           TEXT,
    UNIQUE (request_id)
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='mol_raw' AND table_name='nih_reporter' AND column_name='ingested_at') THEN
        ALTER TABLE mol_raw.nih_reporter ADD COLUMN ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_mol_raw_nih_reporter_processed ON mol_raw.nih_reporter (processed_to_bronze);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='mol_raw' AND table_name='nih_reporter' AND column_name='ingested_at') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_mol_raw_nih_reporter_ingested ON mol_raw.nih_reporter (ingested_at)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_mol_raw_nih_reporter_ingested_brin
                 ON mol_raw.nih_reporter USING BRIN (ingested_at) WITH (pages_per_range = 128)';
    END IF;
END $$;

COMMIT;
