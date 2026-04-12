-- Migration 162: Create missing mol_raw tables for europepmc and nih_reporter
-- Both bronze models reference these raw tables but no DDL existed (audit Bucket C.1).
-- Both fetchers follow the standard envelope pattern (request_id, response_body JSONB,
-- response_status, etc.) used by bindingdb / chembl_activities / clinicaltrials in
-- migration 137.

BEGIN;

-- ============================================================================
-- mol_raw.europepmc — EuropePMC literature search results
-- Bronze upstream: mol_bronze.europepmc
-- Fetcher: src/dk_data/ingestion/fetchers/europepmc.py
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_europepmc_processed ON mol_raw.europepmc (processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_mol_raw_europepmc_loaded    ON mol_raw.europepmc (_loaded_at);

-- ============================================================================
-- mol_raw.nih_reporter — NIH RePORTER grants API
-- Bronze upstream: mol_bronze.nih_reporter
-- Fetcher: src/dk_data/ingestion/fetchers/nih_reporter.py
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_nih_reporter_processed ON mol_raw.nih_reporter (processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_mol_raw_nih_reporter_ingested  ON mol_raw.nih_reporter (ingested_at);

-- BRIN on ingested_at for incremental processing (matches 035_brin_indexes pattern)
CREATE INDEX IF NOT EXISTS idx_mol_raw_europepmc_ingested_brin
    ON mol_raw.europepmc USING BRIN (_loaded_at) WITH (pages_per_range = 128);
CREATE INDEX IF NOT EXISTS idx_mol_raw_nih_reporter_ingested_brin
    ON mol_raw.nih_reporter USING BRIN (ingested_at) WITH (pages_per_range = 128);

COMMIT;
