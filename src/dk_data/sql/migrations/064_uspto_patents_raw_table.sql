-- Migration: 064_uspto_patents_raw_table
-- Feature: 011-datasource-integration
-- Purpose: Create raw table for USPTO PatentsView patent data (credential-gated source)
-- Run: psql -h localhost -p 5433 -U postgres -d dk_data -f migrations/064_uspto_patents_raw_table.sql

-- =============================================================================
-- raw.uspto_patents — USPTO PatentsView pharmaceutical patents
-- =============================================================================

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

CREATE INDEX IF NOT EXISTS idx_uspto_patents_grant ON raw.uspto_patents(grant_date DESC);
CREATE INDEX IF NOT EXISTS idx_uspto_patents_cpc ON raw.uspto_patents USING GIN(cpc_codes);

-- =============================================================================
-- Migration complete
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 064_uspto_patents_raw_table complete.';
    RAISE NOTICE 'Created raw.uspto_patents table with indexes';
END
$$;
