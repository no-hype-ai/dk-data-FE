-- Migration 028: Raw Layer Tables
-- Purpose: Store unmodified HTTP API responses for audit/compliance/reprocessing
-- Part of DK Molecule Data Platform (012-dk-data-platform)

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create schema for raw layer
CREATE SCHEMA IF NOT EXISTS raw;

-- ============================================================================
-- RAW LAYER: Unmodified API Response Archive
-- ============================================================================

-- Base raw table template (used for all sources)
-- Each source gets its own table following this pattern

-- ClinicalTrials.gov Raw Responses
CREATE TABLE IF NOT EXISTS raw.clinicaltrials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Request context
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    api_version VARCHAR(20) DEFAULT 'v2',
    request_params JSONB,
    request_headers JSONB,

    -- Response (UNMODIFIED)
    response_status INTEGER NOT NULL,
    response_headers JSONB,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms INTEGER,

    -- Processing status
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,

    -- Metadata
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'clinicaltrials_gov'
);

CREATE INDEX IF NOT EXISTS idx_raw_ct_request_id ON raw.clinicaltrials(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_ct_timestamp ON raw.clinicaltrials(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_ct_processed ON raw.clinicaltrials(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_ct_hash ON raw.clinicaltrials(response_body_hash);

-- OpenFDA FAERS Raw Responses
CREATE TABLE IF NOT EXISTS raw.openfda_faers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    api_version VARCHAR(20) DEFAULT 'v1',
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'openfda_faers'
);

CREATE INDEX IF NOT EXISTS idx_raw_faers_request_id ON raw.openfda_faers(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_faers_timestamp ON raw.openfda_faers(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_faers_processed ON raw.openfda_faers(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_faers_hash ON raw.openfda_faers(response_body_hash);

-- OpenFDA Labels Raw Responses
CREATE TABLE IF NOT EXISTS raw.openfda_labels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    api_version VARCHAR(20) DEFAULT 'v1',
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'openfda_labels'
);

CREATE INDEX IF NOT EXISTS idx_raw_labels_request_id ON raw.openfda_labels(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_labels_timestamp ON raw.openfda_labels(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_labels_processed ON raw.openfda_labels(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_labels_hash ON raw.openfda_labels(response_body_hash);

-- ChEMBL Raw Responses
CREATE TABLE IF NOT EXISTS raw.chembl (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    api_version VARCHAR(20) DEFAULT 'v1',
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'chembl'
);

CREATE INDEX IF NOT EXISTS idx_raw_chembl_request_id ON raw.chembl(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_chembl_timestamp ON raw.chembl(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_chembl_processed ON raw.chembl(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_chembl_hash ON raw.chembl(response_body_hash);

-- DrugBank Raw Responses
CREATE TABLE IF NOT EXISTS raw.drugbank (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'drugbank'
);

CREATE INDEX IF NOT EXISTS idx_raw_drugbank_request_id ON raw.drugbank(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_drugbank_timestamp ON raw.drugbank(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_drugbank_processed ON raw.drugbank(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_drugbank_hash ON raw.drugbank(response_body_hash);

-- PubChem Raw Responses
CREATE TABLE IF NOT EXISTS raw.pubchem (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'pubchem'
);

CREATE INDEX IF NOT EXISTS idx_raw_pubchem_request_id ON raw.pubchem(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_pubchem_timestamp ON raw.pubchem(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_pubchem_processed ON raw.pubchem(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_pubchem_hash ON raw.pubchem(response_body_hash);

-- UniProt Raw Responses
CREATE TABLE IF NOT EXISTS raw.uniprot (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'uniprot'
);

CREATE INDEX IF NOT EXISTS idx_raw_uniprot_request_id ON raw.uniprot(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_uniprot_timestamp ON raw.uniprot(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_uniprot_processed ON raw.uniprot(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_uniprot_hash ON raw.uniprot(response_body_hash);

-- RCSB PDB Raw Responses
CREATE TABLE IF NOT EXISTS raw.pdb (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'pdb'
);

CREATE INDEX IF NOT EXISTS idx_raw_pdb_request_id ON raw.pdb(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_pdb_timestamp ON raw.pdb(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_pdb_processed ON raw.pdb(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_pdb_hash ON raw.pdb(response_body_hash);

-- SIDER Raw Data (file-based, not API)
CREATE TABLE IF NOT EXISTS raw.sider (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    api_version VARCHAR(20),
    request_params JSONB,
    request_headers JSONB,
    response_status INTEGER NOT NULL DEFAULT 200,
    response_headers JSONB,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    response_size_bytes INTEGER,
    response_time_ms INTEGER,
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'sider'
);

CREATE INDEX IF NOT EXISTS idx_raw_sider_request_id ON raw.sider(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_sider_timestamp ON raw.sider(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_sider_processed ON raw.sider(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_sider_hash ON raw.sider(response_body_hash);

-- OpenAlex Raw Responses
CREATE TABLE IF NOT EXISTS raw.openalex (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'openalex'
);

CREATE INDEX IF NOT EXISTS idx_raw_openalex_request_id ON raw.openalex(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_openalex_timestamp ON raw.openalex(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_openalex_processed ON raw.openalex(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_openalex_hash ON raw.openalex(response_body_hash);

-- ============================================================================
-- DATA SOURCE CONFIGURATION
-- ============================================================================

CREATE TABLE IF NOT EXISTS data_source_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id VARCHAR(50) UNIQUE NOT NULL,
    source_name VARCHAR(200) NOT NULL,
    api_type VARCHAR(20) NOT NULL CHECK (api_type IN ('REST', 'GraphQL', 'Bulk', 'XML', 'File')),
    base_url VARCHAR(500),
    auth_type VARCHAR(20) CHECK (auth_type IN ('none', 'api_key', 'oauth2', 'basic')),
    auth_config JSONB,  -- Encrypted credentials

    -- Scheduling (tiered freshness)
    refresh_tier VARCHAR(20) NOT NULL CHECK (refresh_tier IN ('daily', 'weekly', 'monthly', 'on_demand')),
    cron_schedule VARCHAR(100),
    rate_limit_per_second NUMERIC(5,2),
    retry_max_attempts INTEGER DEFAULT 3,
    retry_backoff_seconds INTEGER DEFAULT 60,

    -- Schema
    schema_mapping JSONB,
    detected_schema JSONB,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    last_successful_sync TIMESTAMPTZ,
    last_error TEXT,
    total_records_synced BIGINT DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default data source configurations
INSERT INTO data_source_config (source_id, source_name, api_type, base_url, auth_type, refresh_tier, rate_limit_per_second)
VALUES
    ('clinicaltrials_gov', 'ClinicalTrials.gov', 'REST', 'https://clinicaltrials.gov/api/v2', 'none', 'daily', 3.0),
    ('openfda_faers', 'OpenFDA FAERS', 'REST', 'https://api.fda.gov/drug/event.json', 'none', 'weekly', 4.0),
    ('openfda_labels', 'OpenFDA Drug Labels', 'REST', 'https://api.fda.gov/drug/label.json', 'none', 'daily', 4.0),
    ('chembl', 'ChEMBL', 'REST', 'https://www.ebi.ac.uk/chembl/api/data', 'none', 'monthly', 1.0),
    ('drugbank', 'DrugBank', 'REST', 'https://go.drugbank.com/releases', 'api_key', 'monthly', 1.0),
    ('pubchem', 'PubChem', 'REST', 'https://pubchem.ncbi.nlm.nih.gov/rest/pug', 'none', 'monthly', 5.0),
    ('uniprot', 'UniProt', 'REST', 'https://rest.uniprot.org', 'none', 'monthly', 25.0),
    ('pdb', 'RCSB PDB', 'REST', 'https://data.rcsb.org/rest/v1', 'none', 'monthly', 10.0),
    ('sider', 'SIDER', 'File', 'http://sideeffects.embl.de', 'none', 'monthly', NULL),
    ('openalex', 'OpenAlex', 'REST', 'https://api.openalex.org', 'none', 'weekly', 10.0)
ON CONFLICT (source_id) DO NOTHING;

-- ============================================================================
-- SYNC JOB TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS sync_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id VARCHAR(50) NOT NULL REFERENCES data_source_config(source_id),
    job_type VARCHAR(20) NOT NULL CHECK (job_type IN ('full', 'incremental', 'manual')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Stats
    records_fetched INTEGER DEFAULT 0,
    records_new INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,

    -- Error tracking
    error_message TEXT,
    error_details JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sync_jobs_source ON sync_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_status ON sync_jobs(status);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_created ON sync_jobs(created_at DESC);

-- Add comment for documentation
COMMENT ON SCHEMA raw IS 'Raw layer: Unmodified API responses for audit/compliance/reprocessing';
COMMENT ON TABLE data_source_config IS 'Configuration for external data sources with tiered refresh schedules';
COMMENT ON TABLE sync_jobs IS 'Tracking table for data synchronization jobs';
