-- Migration: 063_drugbank_raw_table
-- Feature: 011-datasource-integration
-- Purpose: Create raw table for DrugBank drug entries (credential-gated source)
-- Note: raw.drugbank is already created by 028_raw_layer_tables.sql with
-- the standard API-response JSONB schema. This migration adds the table
-- only if it doesn't already exist, then ensures flat columns exist.

-- =============================================================================
-- raw.drugbank — DrugBank drug database entries
-- =============================================================================

-- Attempt to create with flat schema.
-- If migration 028 already created with JSONB schema, this is a no-op.
CREATE TABLE IF NOT EXISTS raw.drugbank (
    drugbank_id VARCHAR(20) NOT NULL,
    name VARCHAR(500),
    description TEXT,
    cas_number VARCHAR(50),
    categories TEXT[],
    targets JSONB,
    enzymes JSONB,
    indication TEXT,
    pharmacodynamics TEXT,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (drugbank_id)
);

-- If the table already existed from 028 (JSONB schema), add flat columns
-- so the loader can INSERT structured records.
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS drugbank_id VARCHAR(20);
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS name VARCHAR(500);
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS cas_number VARCHAR(50);
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS categories TEXT[];
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS targets JSONB;
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS enzymes JSONB;
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS indication TEXT;
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS pharmacodynamics TEXT;
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS _loaded_at TIMESTAMP DEFAULT NOW();
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS _source_file VARCHAR(500);
ALTER TABLE raw.drugbank ADD COLUMN IF NOT EXISTS _source_hash VARCHAR(64);

-- Add unique index on drugbank_id for upsert support (ON CONFLICT).
DO $$
BEGIN
    CREATE UNIQUE INDEX idx_raw_drugbank_uq_drugbank_id
        ON raw.drugbank(drugbank_id);
EXCEPTION WHEN duplicate_table THEN
    NULL;  -- Index already exists
END $$;

-- Indexes are conditional — table may have been created by 028 with different columns
DO $$
BEGIN
    CREATE INDEX IF NOT EXISTS idx_drugbank_name ON raw.drugbank(name);
EXCEPTION WHEN undefined_column THEN
    NULL;  -- Column 'name' not in 028's schema
END $$;

DO $$
BEGIN
    CREATE INDEX IF NOT EXISTS idx_drugbank_cas ON raw.drugbank(cas_number) WHERE cas_number IS NOT NULL;
EXCEPTION WHEN undefined_column THEN
    NULL;  -- Column 'cas_number' not in 028's schema
END $$;

DO $$
BEGIN
    RAISE NOTICE 'Migration 063_drugbank_raw_table complete.';
    RAISE NOTICE 'Created/updated raw.drugbank with flat columns and indexes';
END
$$;
