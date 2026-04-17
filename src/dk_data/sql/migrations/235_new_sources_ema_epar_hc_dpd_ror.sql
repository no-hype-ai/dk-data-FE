-- Migration 235: raw tables for 3 new sources
-- Wave B: hcp-research-sources
--
-- Creates:
--   mol_raw.ema_epar         — EMA EPAR assessment reports
--   mol_raw.health_canada_dpd — Health Canada Drug Product Database
--   hcp_raw schema           — Healthcare professional raw data
--   hcp_raw.research_orgs_ror — Research Organization Registry (ROR)
--
-- Pattern: matches migration 121 standardised mol_raw schema
-- (id UUID, request_id VARCHAR UNIQUE, ..., response_body JSONB, source_id VARCHAR)

BEGIN;

-- ============================================================================
-- 1. hcp_raw SCHEMA (new domain — HCP raw data)
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS hcp_raw;

-- ============================================================================
-- 2. MOL_RAW TABLES
-- ============================================================================

-- 2a. EMA EPAR assessment reports
CREATE TABLE IF NOT EXISTS mol_raw.ema_epar (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'ema_epar',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'ema_epar'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_ema_epar_request_id
    ON mol_raw.ema_epar(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ema_epar_ts
    ON mol_raw.ema_epar(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ema_epar_bronze
    ON mol_raw.ema_epar(processed_to_bronze) WHERE NOT processed_to_bronze;

-- 2b. Health Canada Drug Product Database
CREATE TABLE IF NOT EXISTS mol_raw.health_canada_dpd (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'health_canada_dpd',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'health_canada_dpd'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_hc_dpd_request_id
    ON mol_raw.health_canada_dpd(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_hc_dpd_ts
    ON mol_raw.health_canada_dpd(ingested_at);
CREATE INDEX IF NOT EXISTS idx_mol_raw_hc_dpd_bronze
    ON mol_raw.health_canada_dpd(processed_to_bronze) WHERE NOT processed_to_bronze;

-- ============================================================================
-- 3. HCP_RAW TABLE
-- ============================================================================

-- 3a. Research Organization Registry (ROR)
CREATE TABLE IF NOT EXISTS hcp_raw.research_orgs_ror (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id          VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint        VARCHAR(500) NOT NULL DEFAULT 'research_orgs_ror',
    api_version         VARCHAR(20),
    request_params      JSONB,
    request_headers     JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_headers    JSONB,
    response_body       JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms    INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false,
    processed_at        TIMESTAMPTZ,
    processing_error    TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id           VARCHAR(50) NOT NULL DEFAULT 'research_orgs_ror'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_hcp_raw_ror_request_id
    ON hcp_raw.research_orgs_ror(request_id);
CREATE INDEX IF NOT EXISTS idx_hcp_raw_ror_ts
    ON hcp_raw.research_orgs_ror(ingested_at);
CREATE INDEX IF NOT EXISTS idx_hcp_raw_ror_bronze
    ON hcp_raw.research_orgs_ror(processed_to_bronze) WHERE NOT processed_to_bronze;

-- ============================================================================
-- 4. META REGISTRATION
-- ============================================================================

INSERT INTO meta.data_sources (source_name) VALUES ('ema_epar')
    ON CONFLICT (source_name) DO NOTHING;
INSERT INTO meta.data_sources (source_name) VALUES ('health_canada_dpd')
    ON CONFLICT (source_name) DO NOTHING;
INSERT INTO meta.data_sources (source_name) VALUES ('research_orgs_ror')
    ON CONFLICT (source_name) DO NOTHING;

COMMIT;
