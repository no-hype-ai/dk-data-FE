-- Migration: 063_drugbank_raw_table
-- Feature: 011-datasource-integration
-- Purpose: Create raw table for DrugBank drug entries (credential-gated source)
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/063_drugbank_raw_table.sql

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

CREATE INDEX IF NOT EXISTS idx_drugbank_name ON raw.drugbank(name);
CREATE INDEX IF NOT EXISTS idx_drugbank_cas ON raw.drugbank(cas_number) WHERE cas_number IS NOT NULL;

-- =============================================================================
-- Migration complete
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 063_drugbank_raw_table complete.';
    RAISE NOTICE 'Created raw.drugbank table with indexes';
END
$$;
