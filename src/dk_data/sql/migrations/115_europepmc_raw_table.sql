-- Migration: 085_europepmc_raw_table
-- Feature: 011-datasource-integration
-- Purpose: Create mol_raw.europepmc_raw table for EuropePMC literature ingestion
-- Date: 2026-03-27
--
-- Table stores raw EuropePMC REST API search result objects as JSONB.
-- The unique index on response_body->>'pmid' enables ON CONFLICT deduplication.
-- The bronze.europepmc SQLMesh model extracts typed fields from response_body.

BEGIN;

-- ============================================================================
-- mol_raw.europepmc_raw — EuropePMC search result JSONB blobs
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_raw.europepmc_raw (
    id                  BIGSERIAL PRIMARY KEY,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_status     INTEGER     NOT NULL DEFAULT 200,
    response_body       JSONB       NOT NULL,
    processed_to_bronze BOOLEAN     NOT NULL DEFAULT FALSE,
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Expression index required for ON CONFLICT deduplication in the loader
CREATE UNIQUE INDEX IF NOT EXISTS uidx_europepmc_raw_pmid
    ON mol_raw.europepmc_raw ((response_body->>'pmid'))
    WHERE response_body->>'pmid' IS NOT NULL;

-- Supporting indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_europepmc_raw_loaded_at
    ON mol_raw.europepmc_raw (_loaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_europepmc_raw_processed
    ON mol_raw.europepmc_raw (processed_to_bronze)
    WHERE processed_to_bronze = FALSE;

DO $$
BEGIN
    RAISE NOTICE 'Migration 085_europepmc_raw_table completed successfully';
    RAISE NOTICE 'Created mol_raw.europepmc_raw with expression index on pmid';
END $$;

COMMIT;
