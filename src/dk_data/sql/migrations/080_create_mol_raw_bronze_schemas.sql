-- Migration 080: Create additional raw/bronze tables for MCP pipeline
-- Purpose: Add tables not yet covered by earlier migrations (020, 025, 028, 029, 060).
--          mol_raw.* tables already exist from 020; most raw.* from 025/028/060;
--          most bronze.* from 029/050. Only genuinely new tables are created here.
-- Part of: 015-assessment-dashboard-integration
--
-- REMOVED DUPLICATES (these already exist in earlier migrations):
--   mol_raw.* (all 10 tables) — migration 020
--   raw.pubmed, raw.sec_edgar, raw.hta_decisions, raw.epo_patents — migration 060
--   raw.orange_book, raw.ema, raw.uspto_patents — migration 025
--   raw.orcid — migration 066
--   raw.who_icd — migration 075
--   bronze.clinicaltrials, bronze.openfda_*, bronze.chembl, bronze.drugbank,
--     bronze.pubchem, bronze.openalex — migration 029
--   bronze.orange_book — migration 050

-- ============================================================================
-- 1. New raw.* tables — sources not in any earlier migration
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw.cochrane (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    request_params JSONB,
    response_status INTEGER NOT NULL DEFAULT 200,
    response_body JSONB NOT NULL,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_raw_cochrane_req ON raw.cochrane(request_id);

-- ============================================================================
-- 2. New bronze.* tables — typed extracts not in migration 029/050
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.pubmed (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    pmid VARCHAR(20) NOT NULL,
    title TEXT,
    abstract TEXT,
    authors JSONB,
    journal VARCHAR(500),
    pub_date DATE,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(pmid)
);
CREATE INDEX IF NOT EXISTS idx_bronze_pubmed_pmid ON bronze.pubmed(pmid);

-- ============================================================================
-- 3. GRANTS — ensure roles can access the new tables
-- ============================================================================
-- Note: web_anon is intentionally excluded from raw/bronze/silver grants
-- per security policy (commit 4b78e3c, migration 077). Only authenticated
-- roles (analyst, api_user) should access data layer tables.

DO $$
BEGIN
    -- Grant dk_app access for ingestion pipelines
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'dk_app') THEN
        GRANT USAGE ON SCHEMA mol_raw TO dk_app;
        GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA mol_raw TO dk_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA mol_raw GRANT SELECT, INSERT ON TABLES TO dk_app;

        GRANT USAGE ON SCHEMA bronze TO dk_app;
        GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA bronze TO dk_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA bronze GRANT SELECT, INSERT ON TABLES TO dk_app;
    END IF;

    -- Grant authenticator access for PostgREST role switching
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
        GRANT USAGE ON SCHEMA mol_raw TO authenticator;
        GRANT SELECT ON ALL TABLES IN SCHEMA mol_raw TO authenticator;

        GRANT USAGE ON SCHEMA bronze TO authenticator;
        GRANT SELECT ON ALL TABLES IN SCHEMA bronze TO authenticator;
    END IF;
END $$;

COMMENT ON SCHEMA mol_raw IS 'Raw layer: Unmodified molecule-specific API responses';
COMMENT ON SCHEMA bronze IS 'Bronze layer: Typed columns extracted from raw JSONB';
