-- Migration 080: Create mol_raw schema and additional raw/bronze tables
-- Purpose: MCP tools target mol_raw.* for molecule-specific sources,
--          raw.* for non-molecule sources. Bronze tables extract typed columns.
-- Part of: Fix MCP → Raw → Bronze → Silver → Gold data pipeline

-- ============================================================================
-- 1. mol_raw SCHEMA — molecule-specific raw API responses
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS mol_raw;

-- Shared column pattern:
--   id UUID PK, request_id, request_timestamp, api_endpoint,
--   request_params JSONB, response_status INT, response_body JSONB,
--   processed_to_bronze BOOL, ingested_at TIMESTAMPTZ

CREATE TABLE IF NOT EXISTS mol_raw.clinicaltrials (
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_ct_req ON mol_raw.clinicaltrials(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ct_proc ON mol_raw.clinicaltrials(processed_to_bronze);

CREATE TABLE IF NOT EXISTS mol_raw.openfda_faers (
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_faers_req ON mol_raw.openfda_faers(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_faers_proc ON mol_raw.openfda_faers(processed_to_bronze);

CREATE TABLE IF NOT EXISTS mol_raw.openfda_labels (
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_labels_req ON mol_raw.openfda_labels(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_labels_proc ON mol_raw.openfda_labels(processed_to_bronze);

CREATE TABLE IF NOT EXISTS mol_raw.chembl (
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_chembl_req ON mol_raw.chembl(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_chembl_proc ON mol_raw.chembl(processed_to_bronze);

CREATE TABLE IF NOT EXISTS mol_raw.drugbank (
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_drugbank_req ON mol_raw.drugbank(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_drugbank_proc ON mol_raw.drugbank(processed_to_bronze);

CREATE TABLE IF NOT EXISTS mol_raw.pubchem (
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_pubchem_req ON mol_raw.pubchem(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_pubchem_proc ON mol_raw.pubchem(processed_to_bronze);

CREATE TABLE IF NOT EXISTS mol_raw.uniprot (
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_uniprot_req ON mol_raw.uniprot(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_uniprot_proc ON mol_raw.uniprot(processed_to_bronze);

CREATE TABLE IF NOT EXISTS mol_raw.pdb (
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_pdb_req ON mol_raw.pdb(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_pdb_proc ON mol_raw.pdb(processed_to_bronze);

CREATE TABLE IF NOT EXISTS mol_raw.openalex (
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_openalex_req ON mol_raw.openalex(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_openalex_proc ON mol_raw.openalex(processed_to_bronze);

CREATE TABLE IF NOT EXISTS mol_raw.sider (
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
CREATE INDEX IF NOT EXISTS idx_mol_raw_sider_req ON mol_raw.sider(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_sider_proc ON mol_raw.sider(processed_to_bronze);


-- ============================================================================
-- 2. Additional raw.* tables — non-molecule sources
-- ============================================================================
-- (raw schema already exists from migration 028)

CREATE TABLE IF NOT EXISTS raw.pubmed (
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
CREATE INDEX IF NOT EXISTS idx_raw_pubmed_req ON raw.pubmed(request_id);

CREATE TABLE IF NOT EXISTS raw.orange_book (
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
CREATE INDEX IF NOT EXISTS idx_raw_orange_book_req ON raw.orange_book(request_id);

CREATE TABLE IF NOT EXISTS raw.ema (
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
CREATE INDEX IF NOT EXISTS idx_raw_ema_req ON raw.ema(request_id);

CREATE TABLE IF NOT EXISTS raw.sec_edgar (
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
CREATE INDEX IF NOT EXISTS idx_raw_sec_edgar_req ON raw.sec_edgar(request_id);

CREATE TABLE IF NOT EXISTS raw.orcid (
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
CREATE INDEX IF NOT EXISTS idx_raw_orcid_req ON raw.orcid(request_id);

CREATE TABLE IF NOT EXISTS raw.who_icd (
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
CREATE INDEX IF NOT EXISTS idx_raw_who_icd_req ON raw.who_icd(request_id);

CREATE TABLE IF NOT EXISTS raw.hta_decisions (
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
CREATE INDEX IF NOT EXISTS idx_raw_hta_decisions_req ON raw.hta_decisions(request_id);

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

CREATE TABLE IF NOT EXISTS raw.epo_patents (
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
CREATE INDEX IF NOT EXISTS idx_raw_epo_patents_req ON raw.epo_patents(request_id);

CREATE TABLE IF NOT EXISTS raw.uspto_patents (
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
CREATE INDEX IF NOT EXISTS idx_raw_uspto_patents_req ON raw.uspto_patents(request_id);


-- ============================================================================
-- 3. bronze.* tables — typed columns extracted from raw JSONB
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.clinicaltrials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    nct_id VARCHAR(15) NOT NULL,
    title TEXT,
    phase VARCHAR(30),
    enrollment INTEGER,
    sponsor VARCHAR(500),
    status VARCHAR(50),
    conditions JSONB,
    interventions JSONB,
    start_date DATE,
    completion_date DATE,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(nct_id)
);
CREATE INDEX IF NOT EXISTS idx_bronze_ct_nct ON bronze.clinicaltrials(nct_id);
CREATE INDEX IF NOT EXISTS idx_bronze_ct_phase ON bronze.clinicaltrials(phase);

CREATE TABLE IF NOT EXISTS bronze.openfda_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    set_id VARCHAR(50) NOT NULL,
    brand_name TEXT,
    generic_name TEXT,
    indications TEXT,
    adverse_reactions TEXT,
    dosage TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(set_id)
);
CREATE INDEX IF NOT EXISTS idx_bronze_labels_set ON bronze.openfda_labels(set_id);

CREATE TABLE IF NOT EXISTS bronze.openfda_faers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    safety_report_id VARCHAR(50) NOT NULL,
    reactions JSONB,
    outcomes JSONB,
    seriousness INTEGER,
    drugs JSONB,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(safety_report_id)
);
CREATE INDEX IF NOT EXISTS idx_bronze_faers_report ON bronze.openfda_faers(safety_report_id);

CREATE TABLE IF NOT EXISTS bronze.chembl (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    molecule_chembl_id VARCHAR(20) NOT NULL,
    pref_name VARCHAR(500),
    max_phase NUMERIC,
    molecular_weight NUMERIC(12,4),
    canonical_smiles TEXT,
    molecule_type VARCHAR(50),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(molecule_chembl_id)
);
CREATE INDEX IF NOT EXISTS idx_bronze_chembl_id ON bronze.chembl(molecule_chembl_id);

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

CREATE TABLE IF NOT EXISTS bronze.openalex (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    work_id VARCHAR(50) NOT NULL,
    title TEXT,
    doi VARCHAR(200),
    authors JSONB,
    cited_by_count INTEGER,
    publication_year INTEGER,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(work_id)
);
CREATE INDEX IF NOT EXISTS idx_bronze_openalex_work ON bronze.openalex(work_id);

CREATE TABLE IF NOT EXISTS bronze.orange_book (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    application_number VARCHAR(20) NOT NULL,
    product_name TEXT,
    active_ingredient TEXT,
    approval_date DATE,
    applicant VARCHAR(500),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bronze_ob_app ON bronze.orange_book(application_number);

CREATE TABLE IF NOT EXISTS bronze.drugbank (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    drugbank_id VARCHAR(20) NOT NULL,
    name VARCHAR(500),
    description TEXT,
    indication TEXT,
    pharmacodynamics TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(drugbank_id)
);
CREATE INDEX IF NOT EXISTS idx_bronze_drugbank_id ON bronze.drugbank(drugbank_id);

CREATE TABLE IF NOT EXISTS bronze.pubchem (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID,
    cid VARCHAR(20) NOT NULL,
    iupac_name TEXT,
    canonical_smiles TEXT,
    molecular_formula VARCHAR(200),
    molecular_weight NUMERIC(12,4),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(cid)
);
CREATE INDEX IF NOT EXISTS idx_bronze_pubchem_cid ON bronze.pubchem(cid);


-- ============================================================================
-- 4. GRANTS — allow dk_app, authenticator, web_anon to SELECT/INSERT
-- ============================================================================

-- mol_raw schema
GRANT USAGE ON SCHEMA mol_raw TO dk_app, authenticator, web_anon;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA mol_raw TO dk_app;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_raw TO authenticator, web_anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_raw GRANT SELECT, INSERT ON TABLES TO dk_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_raw GRANT SELECT ON TABLES TO authenticator, web_anon;

-- raw schema (additional tables)
GRANT USAGE ON SCHEMA raw TO dk_app, authenticator, web_anon;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA raw TO dk_app;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO authenticator, web_anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT, INSERT ON TABLES TO dk_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT ON TABLES TO authenticator, web_anon;

-- bronze schema
GRANT USAGE ON SCHEMA bronze TO dk_app, authenticator, web_anon;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA bronze TO dk_app;
GRANT SELECT ON ALL TABLES IN SCHEMA bronze TO authenticator, web_anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA bronze GRANT SELECT, INSERT ON TABLES TO dk_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA bronze GRANT SELECT ON TABLES TO authenticator, web_anon;

-- Ensure silver and gold schemas are also accessible
GRANT USAGE ON SCHEMA silver TO dk_app, authenticator, web_anon;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA silver TO dk_app;
GRANT SELECT ON ALL TABLES IN SCHEMA silver TO authenticator, web_anon;

COMMENT ON SCHEMA mol_raw IS 'Raw layer: Unmodified molecule-specific API responses';
COMMENT ON SCHEMA bronze IS 'Bronze layer: Typed columns extracted from raw JSONB';
