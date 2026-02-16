-- Migration: 064_uspto_patents_raw_table
-- Feature: 011-datasource-integration
-- Purpose: Create raw table for USPTO PatentsView patent data (credential-gated source)
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/064_uspto_patents_raw_table.sql

-- =============================================================================
-- raw.uspto_patents — USPTO PatentsView pharmaceutical patents
-- =============================================================================

-- Attempt to create with flat schema.
-- If migration 025 already created this table with JSONB-envelope schema,
-- CREATE TABLE IF NOT EXISTS silently skips and we add flat columns below.
CREATE TABLE IF NOT EXISTS raw.uspto_patents (
    patent_number VARCHAR(50) NOT NULL,
    title TEXT,
    abstract TEXT,
    inventors JSONB,
    assignees JSONB,
    filing_date DATE,
    grant_date DATE,
    cpc_codes TEXT[],
    claims_count INTEGER,
    _loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    _source_file VARCHAR(500),
    _source_hash VARCHAR(64),
    UNIQUE (patent_number)
);

-- If the table already existed from 025 (JSONB schema), add flat columns
-- so the loader can INSERT structured records alongside the JSONB rows.
-- ADD COLUMN IF NOT EXISTS is safe — no-op when columns already exist.
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS patent_number VARCHAR(50);
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS abstract TEXT;
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS inventors JSONB;
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS assignees JSONB;
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS filing_date DATE;
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS grant_date DATE;
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS cpc_codes TEXT[];
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS claims_count INTEGER;
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS _loaded_at TIMESTAMP DEFAULT NOW();
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS _source_file VARCHAR(500);
ALTER TABLE raw.uspto_patents ADD COLUMN IF NOT EXISTS _source_hash VARCHAR(64);

-- Add unique index on patent_number for upsert support (ON CONFLICT).
-- PostgreSQL treats NULLs as distinct, so existing JSONB rows with NULL
-- patent_number won't conflict with each other or with inserted flat rows.
DO $$
BEGIN
    CREATE UNIQUE INDEX idx_raw_uspto_patents_uq_patent_number
        ON raw.uspto_patents(patent_number);
EXCEPTION WHEN duplicate_table THEN
    NULL;  -- Index already exists
END $$;

-- Indexes are conditional — safe even if columns were just added
DO $$
BEGIN
    CREATE INDEX IF NOT EXISTS idx_uspto_patents_grant ON raw.uspto_patents(grant_date DESC);
EXCEPTION WHEN undefined_column THEN
    NULL;
END $$;

DO $$
BEGIN
    CREATE INDEX IF NOT EXISTS idx_uspto_patents_cpc ON raw.uspto_patents USING GIN(cpc_codes);
EXCEPTION WHEN undefined_column THEN
    NULL;
END $$;

-- =============================================================================
-- Migration complete
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 064_uspto_patents_raw_table complete.';
    RAISE NOTICE 'Created/updated raw.uspto_patents table with flat columns and indexes';
END
$$;
