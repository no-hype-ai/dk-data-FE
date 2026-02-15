-- Migration: 062_mol_source_raw_tables
-- Feature: 011-datasource-integration
-- Purpose: Create missing raw tables for Tier 2A/3 molecule sources
-- Date: 2026-02-14

BEGIN;

-- ============================================================================
-- STEP 1: CREATE MISSING RAW LAYER TABLES (Tier 2A/3 molecule sources)
-- ============================================================================

-- BindingDB Raw Responses
CREATE TABLE IF NOT EXISTS raw.bindingdb (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'bindingdb'
);

CREATE INDEX IF NOT EXISTS idx_raw_bindingdb_request_id ON raw.bindingdb(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_bindingdb_timestamp ON raw.bindingdb(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_bindingdb_processed ON raw.bindingdb(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_bindingdb_hash ON raw.bindingdb(response_body_hash);

-- Orange Book Raw Responses
CREATE TABLE IF NOT EXISTS raw.orange_book (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'orange_book'
);

CREATE INDEX IF NOT EXISTS idx_raw_orange_book_request_id ON raw.orange_book(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_orange_book_timestamp ON raw.orange_book(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_orange_book_processed ON raw.orange_book(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_orange_book_hash ON raw.orange_book(response_body_hash);

-- EMA Raw Responses
CREATE TABLE IF NOT EXISTS raw.ema (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'ema'
);

CREATE INDEX IF NOT EXISTS idx_raw_ema_request_id ON raw.ema(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_ema_timestamp ON raw.ema(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_ema_processed ON raw.ema(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_ema_hash ON raw.ema(response_body_hash);

-- FDA Drugs Raw Responses
CREATE TABLE IF NOT EXISTS raw.fda_drugs (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'fda_drugs'
);

CREATE INDEX IF NOT EXISTS idx_raw_fda_drugs_request_id ON raw.fda_drugs(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_fda_drugs_timestamp ON raw.fda_drugs(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_fda_drugs_processed ON raw.fda_drugs(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_fda_drugs_hash ON raw.fda_drugs(response_body_hash);

-- IMGT Raw Responses
CREATE TABLE IF NOT EXISTS raw.imgt (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'imgt'
);

CREATE INDEX IF NOT EXISTS idx_raw_imgt_request_id ON raw.imgt(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_imgt_timestamp ON raw.imgt(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_imgt_processed ON raw.imgt(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_imgt_hash ON raw.imgt(response_body_hash);

-- CDC Vaccines Raw Responses
CREATE TABLE IF NOT EXISTS raw.cdc_vaccines (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'cdc_vaccines'
);

CREATE INDEX IF NOT EXISTS idx_raw_cdc_vaccines_request_id ON raw.cdc_vaccines(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_cdc_vaccines_timestamp ON raw.cdc_vaccines(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_cdc_vaccines_processed ON raw.cdc_vaccines(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_cdc_vaccines_hash ON raw.cdc_vaccines(response_body_hash);

-- DailyMed Raw Responses
CREATE TABLE IF NOT EXISTS raw.dailymed (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'dailymed'
);

CREATE INDEX IF NOT EXISTS idx_raw_dailymed_request_id ON raw.dailymed(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_dailymed_timestamp ON raw.dailymed(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_dailymed_processed ON raw.dailymed(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_dailymed_hash ON raw.dailymed(response_body_hash);

-- TTD (Therapeutic Target Database) Raw Responses
CREATE TABLE IF NOT EXISTS raw.ttd (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'ttd'
);

CREATE INDEX IF NOT EXISTS idx_raw_ttd_request_id ON raw.ttd(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_ttd_timestamp ON raw.ttd(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_ttd_processed ON raw.ttd(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_ttd_hash ON raw.ttd(response_body_hash);

-- RxNorm Raw Responses
CREATE TABLE IF NOT EXISTS raw.rxnorm (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'rxnorm'
);

CREATE INDEX IF NOT EXISTS idx_raw_rxnorm_request_id ON raw.rxnorm(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_rxnorm_timestamp ON raw.rxnorm(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_rxnorm_processed ON raw.rxnorm(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_rxnorm_hash ON raw.rxnorm(response_body_hash);

-- TDC ADMET Raw Responses
CREATE TABLE IF NOT EXISTS raw.tdc_admet (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'tdc_admet'
);

CREATE INDEX IF NOT EXISTS idx_raw_tdc_admet_request_id ON raw.tdc_admet(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_tdc_admet_timestamp ON raw.tdc_admet(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_tdc_admet_processed ON raw.tdc_admet(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_tdc_admet_hash ON raw.tdc_admet(response_body_hash);

-- PharmGKB Raw Responses
CREATE TABLE IF NOT EXISTS raw.pharmgkb (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'pharmgkb'
);

CREATE INDEX IF NOT EXISTS idx_raw_pharmgkb_request_id ON raw.pharmgkb(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_pharmgkb_timestamp ON raw.pharmgkb(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_pharmgkb_processed ON raw.pharmgkb(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_pharmgkb_hash ON raw.pharmgkb(response_body_hash);

-- KEGG Drug Raw Responses
CREATE TABLE IF NOT EXISTS raw.kegg_drug (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'kegg_drug'
);

CREATE INDEX IF NOT EXISTS idx_raw_kegg_drug_request_id ON raw.kegg_drug(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_kegg_drug_timestamp ON raw.kegg_drug(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_kegg_drug_processed ON raw.kegg_drug(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_kegg_drug_hash ON raw.kegg_drug(response_body_hash);

-- ============================================================================
-- COMPLETION
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 062_mol_source_raw_tables completed successfully';
    RAISE NOTICE 'Created 12 raw tables: bindingdb, orange_book, ema, fda_drugs, imgt, cdc_vaccines, dailymed, ttd, rxnorm, tdc_admet, pharmgkb, kegg_drug';
END $$;

COMMIT;
