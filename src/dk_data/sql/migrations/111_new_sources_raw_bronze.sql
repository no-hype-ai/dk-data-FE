-- Migration 111: Add mol_raw + mol_bronze tables for new data sources
-- Follows medallion pattern: mol_raw (full response) → mol_bronze (typed columns) → mol_silver (entity-linked)
-- Sources: FDA Drugs@FDA, Reactome, KEGG, NICE HTA, CMS Open Payments, Medicare, NIH Reporter, NPI

-- ══════════════════════════════════════════════════════════════════════════
-- mol_raw tables — store full API responses with metadata
-- ══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS mol_raw.fda_drugsfda (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    request_params JSONB,
    response_status INTEGER NOT NULL,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_raw.reactome (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    request_params JSONB,
    response_status INTEGER NOT NULL,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_raw.kegg (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    request_params JSONB,
    response_status INTEGER NOT NULL,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_raw.nice_hta (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    request_params JSONB,
    response_status INTEGER NOT NULL,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_raw.cms_open_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    request_params JSONB,
    response_status INTEGER NOT NULL,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_raw.cms_medicare (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    request_params JSONB,
    response_status INTEGER NOT NULL,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_raw.nih_reporter (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    api_endpoint VARCHAR(500) NOT NULL,
    request_params JSONB,
    response_status INTEGER NOT NULL,
    response_body JSONB NOT NULL,
    response_body_hash VARCHAR(64),
    processed_to_bronze BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ══════════════════════════════════════════════════════════════════════════
-- mol_bronze tables — typed columns extracted from raw JSONB
-- ══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS mol_bronze.fda_drugsfda (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    application_number VARCHAR(20) NOT NULL,
    sponsor_name VARCHAR(500),
    brand_name VARCHAR(500),
    generic_name VARCHAR(500),
    product_type VARCHAR(50),
    dosage_form VARCHAR(200),
    route VARCHAR(200),
    active_ingredients JSONB,
    submission_type VARCHAR(20),
    submission_number VARCHAR(10),
    submission_status VARCHAR(10),
    submission_status_date DATE,
    review_priority VARCHAR(20),
    submission_class_code VARCHAR(20),
    submission_class_description TEXT,
    te_code VARCHAR(20),
    products JSONB,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    UNIQUE(application_number, submission_type, submission_number)
);

CREATE TABLE IF NOT EXISTS mol_bronze.reactome (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    stable_id VARCHAR(50) NOT NULL UNIQUE,
    pathway_name TEXT NOT NULL,
    species VARCHAR(100),
    pathway_type VARCHAR(50),
    diagram_available BOOLEAN,
    has_ehld BOOLEAN,
    parent_pathways JSONB,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mol_bronze.kegg_drugs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    kegg_drug_id VARCHAR(20) NOT NULL UNIQUE,
    drug_name TEXT,
    drug_class TEXT,
    efficacy TEXT,
    drug_type VARCHAR(50),
    targets JSONB,
    pathways JSONB,
    interactions JSONB,
    raw_text TEXT,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mol_bronze.nice_hta (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    guidance_id VARCHAR(50) NOT NULL,
    guidance_type VARCHAR(50),
    title TEXT,
    drug_name VARCHAR(500),
    indication TEXT,
    decision VARCHAR(100),
    decision_date DATE,
    publication_date DATE,
    last_modified DATE,
    url TEXT,
    summary TEXT,
    committee_recommendations TEXT,
    cost_effectiveness_summary TEXT,
    icer_value VARCHAR(100),
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    UNIQUE(guidance_id)
);

CREATE TABLE IF NOT EXISTS mol_bronze.cms_open_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    record_id VARCHAR(50),
    physician_npi VARCHAR(20),
    physician_first_name VARCHAR(200),
    physician_last_name VARCHAR(200),
    physician_specialty VARCHAR(200),
    physician_state VARCHAR(5),
    recipient_type VARCHAR(100),
    manufacturer_name VARCHAR(500),
    product_name VARCHAR(500),
    product_type VARCHAR(100),
    payment_amount NUMERIC(12,2),
    payment_nature VARCHAR(200),
    payment_form VARCHAR(100),
    payment_date DATE,
    payment_year INTEGER,
    program_year INTEGER,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mol_bronze.cms_medicare_spending (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    program VARCHAR(20) NOT NULL,
    brand_name VARCHAR(200),
    generic_name VARCHAR(200),
    year INTEGER NOT NULL,
    total_claims INTEGER,
    total_beneficiaries INTEGER,
    total_spending NUMERIC(14,2),
    total_supply_days INTEGER,
    avg_cost_per_claim NUMERIC(10,2),
    avg_cost_per_day NUMERIC(10,2),
    avg_cost_per_beneficiary NUMERIC(12,2),
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    UNIQUE(program, brand_name, year)
);

CREATE TABLE IF NOT EXISTS mol_bronze.nih_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    project_number VARCHAR(50) NOT NULL,
    project_title TEXT,
    pi_name VARCHAR(500),
    pi_profile_id BIGINT,
    pi_institution VARCHAR(500),
    pi_institution_state VARCHAR(5),
    funding_ic VARCHAR(20),
    funding_agency VARCHAR(100),
    award_amount NUMERIC(14,2),
    fiscal_year INTEGER NOT NULL,
    project_start DATE,
    project_end DATE,
    abstract_text TEXT,
    terms TEXT,
    phr_text TEXT,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE,
    UNIQUE(project_number, fiscal_year)
);

-- Grant PostgREST access
GRANT USAGE ON SCHEMA mol_raw TO analyst;
GRANT USAGE ON SCHEMA mol_bronze TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_raw TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_bronze TO analyst;
