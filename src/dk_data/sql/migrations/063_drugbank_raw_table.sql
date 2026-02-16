-- Migration: 063_drugbank_raw_table
-- Feature: 011-datasource-integration
-- Purpose: Create raw table for DrugBank drug entries (credential-gated source)
-- Note: raw.drugbank is already created by 028_raw_layer_tables.sql with
-- the standard API-response JSONB schema. This migration adds the table
-- only if it doesn't already exist (backward compat for older deploys).

-- =============================================================================
-- raw.drugbank — DrugBank drug database entries
-- =============================================================================

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
END
$$;
