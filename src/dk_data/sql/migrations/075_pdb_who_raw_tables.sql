-- Migration: 075_pdb_who_raw_tables
-- Feature: 015-assessment-dashboard-integration
-- Purpose: Create raw tables for PDB structures and WHO ICD codes (new MCP tool sources)
-- Date: 2026-02-25

BEGIN;

-- =============================================================================
-- raw.pdb_structures — PDB protein structure co-crystal API responses
-- Standard JSONB envelope schema matching existing raw.* tables (migration 025 pattern)
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.pdb_structures (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    api_version VARCHAR(20),
    request_params JSONB,
    request_headers JSONB,
    response_status INTEGER NOT NULL,
    response_headers JSONB,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms INTEGER,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'pdb_structures'
);

CREATE INDEX IF NOT EXISTS idx_raw_pdb_structures_request_id ON raw.pdb_structures(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_pdb_structures_timestamp ON raw.pdb_structures(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_pdb_structures_processed ON raw.pdb_structures(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_pdb_structures_hash ON raw.pdb_structures(response_body_hash);

-- =============================================================================
-- raw.who_icd — WHO ICD-10 code API responses
-- Standard JSONB envelope schema
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.who_icd (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    api_version VARCHAR(20),
    request_params JSONB,
    request_headers JSONB,
    response_status INTEGER NOT NULL,
    response_headers JSONB,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms INTEGER,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'who_icd'
);

CREATE INDEX IF NOT EXISTS idx_raw_who_icd_request_id ON raw.who_icd(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_who_icd_timestamp ON raw.who_icd(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_who_icd_processed ON raw.who_icd(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_who_icd_hash ON raw.who_icd(response_body_hash);

COMMIT;

DO $$
BEGIN
    RAISE NOTICE 'Migration 075_pdb_who_raw_tables complete.';
    RAISE NOTICE 'Created raw.pdb_structures and raw.who_icd tables.';
END $$;
