-- Migration: 030_bronze_tables.sql
-- Description: Create Bronze layer tables for raw data ingestion (Medallion Architecture)
-- Date: 2026-01-23
-- Part of: 012-dk-data-platform

-- ==========================================
-- Data Source Configuration
-- ==========================================

CREATE TABLE IF NOT EXISTS data_source_configs (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(50) UNIQUE NOT NULL,
    source_name VARCHAR(200) NOT NULL,

    -- API Configuration
    api_type VARCHAR(20) NOT NULL CHECK (api_type IN ('REST', 'GraphQL', 'Bulk', 'XML')),
    base_url VARCHAR(500) NOT NULL,
    api_version VARCHAR(20),

    -- Authentication
    auth_type VARCHAR(20) CHECK (auth_type IN ('none', 'api_key', 'oauth2', 'basic')),
    auth_config_encrypted BYTEA, -- AES-256 encrypted credentials

    -- Scheduling
    schedule_cron VARCHAR(100),
    rate_limit_per_second DECIMAL DEFAULT 1.0,
    retry_max_attempts INTEGER DEFAULT 3,
    retry_backoff_seconds INTEGER DEFAULT 60,

    -- Schema Detection
    sample_response JSONB,
    detected_schema JSONB,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    last_successful_sync TIMESTAMPTZ,
    last_error TEXT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_data_source_active ON data_source_configs(is_active) WHERE is_active = TRUE;

-- ==========================================
-- Bronze Base Table Template
-- Each source gets its own table following this pattern
-- ==========================================

-- ClinicalTrials.gov
CREATE TABLE IF NOT EXISTS bronze_clinicaltrials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Ingestion metadata
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'clinicaltrials_gov',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,

    -- Query/request context
    query_params JSONB,
    request_id VARCHAR(100),

    -- Raw response (immutable)
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64), -- SHA-256 for dedup detection

    -- Processing status
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,

    -- Retention
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_ct_ingested_at ON bronze_clinicaltrials(ingested_at);
CREATE INDEX idx_bronze_ct_processed ON bronze_clinicaltrials(processed_to_silver) WHERE processed_to_silver = FALSE;
CREATE INDEX idx_bronze_ct_hash ON bronze_clinicaltrials(raw_data_hash);
CREATE INDEX idx_bronze_ct_expires ON bronze_clinicaltrials(expires_at);

-- OpenFDA Drug Labels
CREATE TABLE IF NOT EXISTS bronze_openfda_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'openfda_labels',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,
    query_params JSONB,
    request_id VARCHAR(100),
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_labels_ingested_at ON bronze_openfda_labels(ingested_at);
CREATE INDEX idx_bronze_labels_processed ON bronze_openfda_labels(processed_to_silver) WHERE processed_to_silver = FALSE;
CREATE INDEX idx_bronze_labels_hash ON bronze_openfda_labels(raw_data_hash);

-- OpenFDA FAERS (Adverse Events)
CREATE TABLE IF NOT EXISTS bronze_openfda_faers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'openfda_faers',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,
    query_params JSONB,
    request_id VARCHAR(100),
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_faers_ingested_at ON bronze_openfda_faers(ingested_at);
CREATE INDEX idx_bronze_faers_processed ON bronze_openfda_faers(processed_to_silver) WHERE processed_to_silver = FALSE;
CREATE INDEX idx_bronze_faers_hash ON bronze_openfda_faers(raw_data_hash);

-- ChEMBL
CREATE TABLE IF NOT EXISTS bronze_chembl (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'chembl',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,
    query_params JSONB,
    request_id VARCHAR(100),
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_chembl_ingested_at ON bronze_chembl(ingested_at);
CREATE INDEX idx_bronze_chembl_processed ON bronze_chembl(processed_to_silver) WHERE processed_to_silver = FALSE;
CREATE INDEX idx_bronze_chembl_hash ON bronze_chembl(raw_data_hash);

-- DrugBank
CREATE TABLE IF NOT EXISTS bronze_drugbank (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'drugbank',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,
    query_params JSONB,
    request_id VARCHAR(100),
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_drugbank_ingested_at ON bronze_drugbank(ingested_at);
CREATE INDEX idx_bronze_drugbank_processed ON bronze_drugbank(processed_to_silver) WHERE processed_to_silver = FALSE;
CREATE INDEX idx_bronze_drugbank_hash ON bronze_drugbank(raw_data_hash);

-- PubChem
CREATE TABLE IF NOT EXISTS bronze_pubchem (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'pubchem',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,
    query_params JSONB,
    request_id VARCHAR(100),
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_pubchem_ingested_at ON bronze_pubchem(ingested_at);
CREATE INDEX idx_bronze_pubchem_processed ON bronze_pubchem(processed_to_silver) WHERE processed_to_silver = FALSE;
CREATE INDEX idx_bronze_pubchem_hash ON bronze_pubchem(raw_data_hash);

-- UniProt
CREATE TABLE IF NOT EXISTS bronze_uniprot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'uniprot',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,
    query_params JSONB,
    request_id VARCHAR(100),
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_uniprot_ingested_at ON bronze_uniprot(ingested_at);
CREATE INDEX idx_bronze_uniprot_processed ON bronze_uniprot(processed_to_silver) WHERE processed_to_silver = FALSE;
CREATE INDEX idx_bronze_uniprot_hash ON bronze_uniprot(raw_data_hash);

-- EMA (European Medicines Agency)
CREATE TABLE IF NOT EXISTS bronze_ema (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'ema',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,
    query_params JSONB,
    request_id VARCHAR(100),
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_ema_ingested_at ON bronze_ema(ingested_at);
CREATE INDEX idx_bronze_ema_processed ON bronze_ema(processed_to_silver) WHERE processed_to_silver = FALSE;

-- Orange Book
CREATE TABLE IF NOT EXISTS bronze_orange_book (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'orange_book',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,
    query_params JSONB,
    request_id VARCHAR(100),
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_ob_ingested_at ON bronze_orange_book(ingested_at);
CREATE INDEX idx_bronze_ob_processed ON bronze_orange_book(processed_to_silver) WHERE processed_to_silver = FALSE;

-- USPTO Patents
CREATE TABLE IF NOT EXISTS bronze_patents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'patents_uspto',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,
    query_params JSONB,
    request_id VARCHAR(100),
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_patents_ingested_at ON bronze_patents(ingested_at);
CREATE INDEX idx_bronze_patents_processed ON bronze_patents(processed_to_silver) WHERE processed_to_silver = FALSE;

-- SIDER (Side Effects)
CREATE TABLE IF NOT EXISTS bronze_sider (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'sider',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,
    query_params JSONB,
    request_id VARCHAR(100),
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_sider_ingested_at ON bronze_sider(ingested_at);
CREATE INDEX idx_bronze_sider_processed ON bronze_sider(processed_to_silver) WHERE processed_to_silver = FALSE;

-- OpenAlex (Publications)
CREATE TABLE IF NOT EXISTS bronze_openalex (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'openalex',
    api_version VARCHAR(20),
    api_endpoint VARCHAR(500),
    http_status INTEGER,
    query_params JSONB,
    request_id VARCHAR(100),
    raw_data JSONB NOT NULL,
    raw_data_hash VARCHAR(64),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX idx_bronze_openalex_ingested_at ON bronze_openalex(ingested_at);
CREATE INDEX idx_bronze_openalex_processed ON bronze_openalex(processed_to_silver) WHERE processed_to_silver = FALSE;

-- ==========================================
-- Ingestion Run Log
-- ==========================================

CREATE TABLE IF NOT EXISTS bronze_ingestion_runs (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(50) NOT NULL REFERENCES data_source_configs(source_id),

    -- Run details
    run_id UUID DEFAULT gen_random_uuid(),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'partial')),

    -- Metrics
    records_fetched INTEGER DEFAULT 0,
    records_stored INTEGER DEFAULT 0,
    records_deduplicated INTEGER DEFAULT 0,
    api_calls_made INTEGER DEFAULT 0,

    -- Errors
    error_count INTEGER DEFAULT 0,
    last_error TEXT,

    -- Query context
    query_params JSONB,
    continuation_token TEXT
);

CREATE INDEX idx_ingestion_runs_source ON bronze_ingestion_runs(source_id);
CREATE INDEX idx_ingestion_runs_status ON bronze_ingestion_runs(status) WHERE status = 'running';
