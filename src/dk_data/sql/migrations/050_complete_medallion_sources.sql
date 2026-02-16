-- Migration: 050_complete_medallion_sources.sql
-- Purpose: Complete the medallion architecture with all 16 data sources
-- This adds missing raw/bronze tables to support full integration
-- Date: 2026-01-26

BEGIN;

-- ============================================================================
-- STEP 1: CREATE MISSING RAW LAYER TABLES
-- ============================================================================

-- RxNorm Raw Responses
CREATE TABLE IF NOT EXISTS raw.rxnorm (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'tdc_admet'
);

CREATE INDEX IF NOT EXISTS idx_raw_tdc_admet_request_id ON raw.tdc_admet(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_tdc_admet_timestamp ON raw.tdc_admet(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_tdc_admet_processed ON raw.tdc_admet(processed_to_bronze);

-- PharmGKB Raw Responses
CREATE TABLE IF NOT EXISTS raw.pharmgkb (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'pharmgkb'
);

CREATE INDEX IF NOT EXISTS idx_raw_pharmgkb_request_id ON raw.pharmgkb(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_pharmgkb_timestamp ON raw.pharmgkb(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_pharmgkb_processed ON raw.pharmgkb(processed_to_bronze);
CREATE INDEX IF NOT EXISTS idx_raw_pharmgkb_hash ON raw.pharmgkb(response_body_hash);

-- WebSearch Raw Responses
CREATE TABLE IF NOT EXISTS raw.websearch (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'websearch'
);

CREATE INDEX IF NOT EXISTS idx_raw_websearch_request_id ON raw.websearch(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_websearch_timestamp ON raw.websearch(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_websearch_processed ON raw.websearch(processed_to_bronze);

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

-- WHO INN Raw Responses
CREATE TABLE IF NOT EXISTS raw.who_inn (
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'who_inn'
);

CREATE INDEX IF NOT EXISTS idx_raw_who_inn_request_id ON raw.who_inn(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_who_inn_timestamp ON raw.who_inn(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_who_inn_processed ON raw.who_inn(processed_to_bronze);

-- ============================================================================
-- STEP 2: CREATE MISSING BRONZE LAYER TABLES
-- ============================================================================

-- RxNorm Bronze Table (normalized drug concepts)
CREATE TABLE IF NOT EXISTS bronze.rxnorm_concepts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.rxnorm(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'rxnorm',

    -- RxNorm identifiers
    rxcui VARCHAR(20) NOT NULL,
    name TEXT,
    tty VARCHAR(20),  -- Term type (IN, BN, SCD, SBD, etc.)
    synonym TEXT,
    suppress VARCHAR(10),

    -- Related concepts
    ingredients JSONB,  -- Related ingredient RxCUIs
    brand_names JSONB,  -- Related brand name RxCUIs
    ndc_codes JSONB,    -- Associated NDC codes
    atc_codes JSONB,    -- ATC classification codes

    -- Drug class info
    drug_classes JSONB,

    -- Interaction data
    interactions_count INTEGER,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(rxcui)
);

CREATE INDEX IF NOT EXISTS idx_bronze_rxnorm_rxcui ON bronze.rxnorm_concepts(rxcui);
CREATE INDEX IF NOT EXISTS idx_bronze_rxnorm_name ON bronze.rxnorm_concepts(name);
CREATE INDEX IF NOT EXISTS idx_bronze_rxnorm_tty ON bronze.rxnorm_concepts(tty);
CREATE INDEX IF NOT EXISTS idx_bronze_rxnorm_processed ON bronze.rxnorm_concepts(processed_to_silver);

-- TDC ADMET Bronze Table
CREATE TABLE IF NOT EXISTS bronze.tdc_admet (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.tdc_admet(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'tdc_admet',

    -- Compound identifiers
    compound_id VARCHAR(100) NOT NULL,
    smiles TEXT,
    inchi TEXT,
    inchi_key VARCHAR(27),

    -- Dataset info
    dataset_name VARCHAR(100) NOT NULL,
    dataset_type VARCHAR(50),  -- absorption, distribution, metabolism, excretion, toxicity

    -- ADMET property values
    property_name VARCHAR(100) NOT NULL,
    property_value NUMERIC,
    property_unit VARCHAR(50),
    property_category VARCHAR(50),  -- e.g., 'good', 'moderate', 'poor'

    -- Model info
    model_name VARCHAR(100),
    model_version VARCHAR(20),
    prediction_confidence NUMERIC(5,4),

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_bronze_tdc_compound ON bronze.tdc_admet(compound_id);
CREATE INDEX IF NOT EXISTS idx_bronze_tdc_smiles ON bronze.tdc_admet(smiles);
CREATE INDEX IF NOT EXISTS idx_bronze_tdc_inchi_key ON bronze.tdc_admet(inchi_key);
CREATE INDEX IF NOT EXISTS idx_bronze_tdc_dataset ON bronze.tdc_admet(dataset_name);
CREATE INDEX IF NOT EXISTS idx_bronze_tdc_property ON bronze.tdc_admet(property_name);
CREATE INDEX IF NOT EXISTS idx_bronze_tdc_processed ON bronze.tdc_admet(processed_to_silver);

-- PharmGKB Bronze Table
CREATE TABLE IF NOT EXISTS bronze.pharmgkb (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.pharmgkb(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'pharmgkb',

    -- PharmGKB identifiers
    pharmgkb_id VARCHAR(20) NOT NULL,
    name VARCHAR(500),
    entity_type VARCHAR(50),  -- drug, gene, variant, etc.

    -- Cross-references
    drugbank_id VARCHAR(20),
    chembl_id VARCHAR(20),
    rxnorm_id VARCHAR(20),
    pubchem_cid BIGINT,
    cas_number VARCHAR(20),

    -- Drug info
    drug_type VARCHAR(50),
    smiles TEXT,
    inchi_key VARCHAR(27),

    -- Clinical annotations
    clinical_annotations JSONB,
    dosing_guidelines JSONB,
    drug_labels JSONB,

    -- Variant annotations
    variant_annotations JSONB,

    -- Pathways
    pathways JSONB,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(pharmgkb_id)
);

CREATE INDEX IF NOT EXISTS idx_bronze_pharmgkb_id ON bronze.pharmgkb(pharmgkb_id);
CREATE INDEX IF NOT EXISTS idx_bronze_pharmgkb_name ON bronze.pharmgkb(name);
CREATE INDEX IF NOT EXISTS idx_bronze_pharmgkb_drugbank ON bronze.pharmgkb(drugbank_id);
CREATE INDEX IF NOT EXISTS idx_bronze_pharmgkb_chembl ON bronze.pharmgkb(chembl_id);
CREATE INDEX IF NOT EXISTS idx_bronze_pharmgkb_inchi ON bronze.pharmgkb(inchi_key);
CREATE INDEX IF NOT EXISTS idx_bronze_pharmgkb_processed ON bronze.pharmgkb(processed_to_silver);

-- WebSearch Bronze Table
CREATE TABLE IF NOT EXISTS bronze.websearch_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.websearch(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'websearch',

    -- Search context
    search_query TEXT NOT NULL,
    search_engine VARCHAR(50) NOT NULL,
    search_type VARCHAR(50),  -- news, academic, general

    -- Result info
    result_url TEXT NOT NULL,
    result_title TEXT,
    result_snippet TEXT,
    result_rank INTEGER,
    result_domain VARCHAR(200),

    -- Publication info (if academic)
    publication_date DATE,
    authors JSONB,
    source_name VARCHAR(500),

    -- Relevance
    relevance_score NUMERIC(5,4),
    molecule_mentions JSONB,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_bronze_websearch_query ON bronze.websearch_results(search_query);
CREATE INDEX IF NOT EXISTS idx_bronze_websearch_url ON bronze.websearch_results(result_url);
CREATE INDEX IF NOT EXISTS idx_bronze_websearch_date ON bronze.websearch_results(publication_date);
CREATE INDEX IF NOT EXISTS idx_bronze_websearch_processed ON bronze.websearch_results(processed_to_silver);

-- KEGG Drug Bronze Table
CREATE TABLE IF NOT EXISTS bronze.kegg_drug (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.kegg_drug(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'kegg_drug',

    -- KEGG identifiers
    kegg_id VARCHAR(20) NOT NULL,  -- D00001 format
    name VARCHAR(500),
    formula VARCHAR(200),
    exact_mass NUMERIC(15,6),

    -- Structure
    smiles TEXT,
    inchi TEXT,
    inchi_key VARCHAR(27),

    -- Classification
    drug_class JSONB,
    atc_codes JSONB,
    therapeutic_target TEXT,

    -- Targets and pathways
    targets JSONB,
    pathways JSONB,
    enzymes JSONB,

    -- External links
    drugbank_id VARCHAR(20),
    pubchem_sid BIGINT,
    chembl_id VARCHAR(20),
    cas_number VARCHAR(20),

    -- Research code mappings
    research_codes JSONB,
    synonyms JSONB,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(kegg_id)
);

CREATE INDEX IF NOT EXISTS idx_bronze_kegg_id ON bronze.kegg_drug(kegg_id);
CREATE INDEX IF NOT EXISTS idx_bronze_kegg_name ON bronze.kegg_drug(name);
CREATE INDEX IF NOT EXISTS idx_bronze_kegg_inchi ON bronze.kegg_drug(inchi_key);
CREATE INDEX IF NOT EXISTS idx_bronze_kegg_drugbank ON bronze.kegg_drug(drugbank_id);
CREATE INDEX IF NOT EXISTS idx_bronze_kegg_processed ON bronze.kegg_drug(processed_to_silver);

-- WHO INN Bronze Table
CREATE TABLE IF NOT EXISTS bronze.who_inn (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.who_inn(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'who_inn',

    -- INN identifiers
    inn_name VARCHAR(500) NOT NULL,
    inn_latin VARCHAR(500),
    inn_list_number INTEGER,  -- The INN list it was published in
    inn_year INTEGER,

    -- Chemical info
    cas_number VARCHAR(20),
    molecular_formula VARCHAR(200),
    smiles TEXT,
    inchi_key VARCHAR(27),

    -- Stem info
    inn_stem VARCHAR(100),
    stem_definition TEXT,

    -- Research code mappings (critical for clinical trials)
    research_codes JSONB,  -- e.g., ['CP-690,550', 'PF-02341066']

    -- Synonyms
    synonyms JSONB,
    brand_names JSONB,

    -- Status
    status VARCHAR(50),  -- proposed, recommended, published

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(inn_name)
);

CREATE INDEX IF NOT EXISTS idx_bronze_inn_name ON bronze.who_inn(inn_name);
CREATE INDEX IF NOT EXISTS idx_bronze_inn_cas ON bronze.who_inn(cas_number);
CREATE INDEX IF NOT EXISTS idx_bronze_inn_inchi ON bronze.who_inn(inchi_key);
CREATE INDEX IF NOT EXISTS idx_bronze_inn_stem ON bronze.who_inn(inn_stem);
CREATE INDEX IF NOT EXISTS idx_bronze_inn_research_codes ON bronze.who_inn USING GIN(research_codes);
CREATE INDEX IF NOT EXISTS idx_bronze_inn_processed ON bronze.who_inn(processed_to_silver);

-- BindingDB Bronze Table (extends existing if needed)
CREATE TABLE IF NOT EXISTS bronze.bindingdb (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'bindingdb',

    -- BindingDB identifiers
    bindingdb_id VARCHAR(50) NOT NULL,
    ligand_name VARCHAR(500),

    -- Structure
    smiles TEXT,
    inchi TEXT,
    inchi_key VARCHAR(27),

    -- Target info
    target_name TEXT,
    target_source VARCHAR(50),
    target_source_id VARCHAR(50),
    target_organism VARCHAR(200),

    -- Binding affinity data
    ki_nm NUMERIC,
    kd_nm NUMERIC,
    ic50_nm NUMERIC,
    ec50_nm NUMERIC,

    -- Activity details
    activity_type VARCHAR(50),
    activity_value NUMERIC,
    activity_unit VARCHAR(50),

    -- Publication info
    pmid VARCHAR(20),
    doi VARCHAR(200),
    patent_id VARCHAR(100),

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(bindingdb_id)
);

CREATE INDEX IF NOT EXISTS idx_bronze_bindingdb_id ON bronze.bindingdb(bindingdb_id);
CREATE INDEX IF NOT EXISTS idx_bronze_bindingdb_inchi ON bronze.bindingdb(inchi_key);
CREATE INDEX IF NOT EXISTS idx_bronze_bindingdb_target ON bronze.bindingdb(target_source_id);
CREATE INDEX IF NOT EXISTS idx_bronze_bindingdb_processed ON bronze.bindingdb(processed_to_silver);

-- EMA Bronze Table
CREATE TABLE IF NOT EXISTS bronze.ema (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'ema',

    -- EMA identifiers
    product_number VARCHAR(50) NOT NULL,
    product_name VARCHAR(500),
    active_substance VARCHAR(500),
    inn VARCHAR(500),
    atc_code VARCHAR(20),

    -- Authorization info
    marketing_authorization_holder VARCHAR(500),
    authorization_status VARCHAR(50),
    authorization_date DATE,
    revision_date DATE,

    -- Classification
    medicine_type VARCHAR(100),
    therapeutic_area VARCHAR(500),
    pharmacotherapeutic_group TEXT,

    -- URLs
    epar_url TEXT,
    summary_url TEXT,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(product_number)
);

CREATE INDEX IF NOT EXISTS idx_bronze_ema_product ON bronze.ema(product_number);
CREATE INDEX IF NOT EXISTS idx_bronze_ema_name ON bronze.ema(product_name);
CREATE INDEX IF NOT EXISTS idx_bronze_ema_inn ON bronze.ema(inn);
CREATE INDEX IF NOT EXISTS idx_bronze_ema_processed ON bronze.ema(processed_to_silver);

-- Orange Book Bronze Table
CREATE TABLE IF NOT EXISTS bronze.orange_book (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'orange_book',

    -- Product identifiers
    application_number VARCHAR(20) NOT NULL,
    product_number VARCHAR(10) NOT NULL DEFAULT '001',
    ingredient VARCHAR(500),
    trade_name VARCHAR(500),
    applicant VARCHAR(500),

    -- Product details
    strength VARCHAR(200),
    dosage_form VARCHAR(100),
    route VARCHAR(100),
    approval_date DATE,
    te_code VARCHAR(20),
    rld VARCHAR(10),

    -- Patent info
    patent_number VARCHAR(50),
    patent_expiration DATE,
    drug_substance_patent BOOLEAN,
    drug_product_patent BOOLEAN,
    patent_use_code VARCHAR(20),

    -- Exclusivity info
    exclusivity_code VARCHAR(20),
    exclusivity_date DATE,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bronze_ob_unique
    ON bronze.orange_book(application_number, product_number, COALESCE(patent_number, ''));
CREATE INDEX IF NOT EXISTS idx_bronze_ob_app ON bronze.orange_book(application_number);
CREATE INDEX IF NOT EXISTS idx_bronze_ob_ingredient ON bronze.orange_book(ingredient);
CREATE INDEX IF NOT EXISTS idx_bronze_ob_trade ON bronze.orange_book(trade_name);
CREATE INDEX IF NOT EXISTS idx_bronze_ob_patent ON bronze.orange_book(patent_number);
CREATE INDEX IF NOT EXISTS idx_bronze_ob_processed ON bronze.orange_book(processed_to_silver);

-- USPTO Patents Bronze Table
CREATE TABLE IF NOT EXISTS bronze.uspto_patents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'uspto_patents',

    -- Patent identifiers
    patent_number VARCHAR(20) NOT NULL,
    patent_title TEXT,
    patent_abstract TEXT,
    patent_date DATE,

    -- Classification
    patent_type VARCHAR(50),
    patent_kind VARCHAR(10),
    cpc_codes JSONB,

    -- Assignee info
    assignee_organization VARCHAR(500),
    assignee_type VARCHAR(50),

    -- Inventors
    inventors JSONB,
    num_claims INTEGER,

    -- Pharma relevance
    is_pharma_related BOOLEAN,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(patent_number)
);

CREATE INDEX IF NOT EXISTS idx_bronze_uspto_number ON bronze.uspto_patents(patent_number);
CREATE INDEX IF NOT EXISTS idx_bronze_uspto_assignee ON bronze.uspto_patents(assignee_organization);
CREATE INDEX IF NOT EXISTS idx_bronze_uspto_date ON bronze.uspto_patents(patent_date);
CREATE INDEX IF NOT EXISTS idx_bronze_uspto_pharma ON bronze.uspto_patents(is_pharma_related);
CREATE INDEX IF NOT EXISTS idx_bronze_uspto_processed ON bronze.uspto_patents(processed_to_silver);

-- ============================================================================
-- STEP 3: UPDATE DATA SOURCE CONFIGURATION
-- ============================================================================

INSERT INTO data_source_config (source_id, source_name, api_type, base_url, auth_type, refresh_tier, rate_limit_per_second)
VALUES
    ('rxnorm', 'RxNorm', 'REST', 'https://rxnav.nlm.nih.gov/REST', 'none', 'weekly', 10.0),
    ('tdc_admet', 'TDC ADMET', 'File', 'https://tdcommons.ai', 'none', 'monthly', NULL),
    ('pharmgkb', 'PharmGKB', 'REST', 'https://api.pharmgkb.org/v1/data', 'none', 'monthly', 5.0),
    ('websearch', 'Web Search', 'REST', NULL, 'api_key', 'on_demand', 1.0),
    ('kegg_drug', 'KEGG Drug', 'REST', 'https://rest.kegg.jp', 'none', 'monthly', 5.0),
    ('who_inn', 'WHO INN', 'File', 'https://www.who.int/medicines', 'none', 'monthly', NULL),
    ('bindingdb', 'BindingDB', 'REST', 'https://www.bindingdb.org/axis2/services/BDBService', 'none', 'monthly', 1.0),
    ('ema', 'EMA', 'REST', 'https://api.ema.europa.eu/api', 'none', 'weekly', 5.0),
    ('orange_book', 'FDA Orange Book', 'File', 'https://www.fda.gov/media', 'none', 'weekly', NULL),
    ('uspto_patents', 'USPTO Patents', 'REST', 'https://api.patentsview.org', 'none', 'weekly', 5.0)
ON CONFLICT (source_id) DO UPDATE SET
    base_url = EXCLUDED.base_url,
    refresh_tier = EXCLUDED.refresh_tier,
    updated_at = NOW();

-- ============================================================================
-- STEP 4: CREATE SILVER LAYER TABLES FOR NEW SOURCES
-- ============================================================================

-- Silver ADMET Predictions Table
CREATE TABLE IF NOT EXISTS silver.admet_predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    molecule_id UUID REFERENCES silver.molecules(id),
    inchi_key VARCHAR(27),

    -- ADMET property
    property_name VARCHAR(100) NOT NULL,
    property_category VARCHAR(50),  -- absorption, distribution, metabolism, excretion, toxicity

    -- Prediction values
    predicted_value NUMERIC,
    predicted_class VARCHAR(50),
    confidence NUMERIC(5,4),
    unit VARCHAR(50),

    -- Source info
    source VARCHAR(50) NOT NULL DEFAULT 'tdc_admet',
    model_name VARCHAR(100),
    model_version VARCHAR(20),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(molecule_id, property_name, source)
);

CREATE INDEX IF NOT EXISTS idx_silver_admet_molecule ON silver.admet_predictions(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_admet_inchi ON silver.admet_predictions(inchi_key);
CREATE INDEX IF NOT EXISTS idx_silver_admet_property ON silver.admet_predictions(property_name);
CREATE INDEX IF NOT EXISTS idx_silver_admet_category ON silver.admet_predictions(property_category);

-- Silver Pharmacogenomics Table
CREATE TABLE IF NOT EXISTS silver.pharmacogenomics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    molecule_id UUID REFERENCES silver.molecules(id),

    -- Gene/Variant info
    gene_symbol VARCHAR(50) NOT NULL,
    variant_id VARCHAR(100),  -- rs number or HGVS
    variant_type VARCHAR(50),  -- SNP, haplotype, etc.

    -- Phenotype/Annotation
    phenotype_category VARCHAR(100),  -- toxicity, efficacy, dosage, metabolism
    clinical_annotation TEXT,
    level_of_evidence VARCHAR(50),  -- 1A, 1B, 2A, 2B, 3, 4

    -- Dosing recommendation
    has_dosing_guideline BOOLEAN DEFAULT FALSE,
    dosing_recommendation TEXT,

    -- Source info
    source VARCHAR(50) NOT NULL DEFAULT 'pharmgkb',
    pharmgkb_annotation_id VARCHAR(50),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(molecule_id, gene_symbol, variant_id, source)
);

CREATE INDEX IF NOT EXISTS idx_silver_pgx_molecule ON silver.pharmacogenomics(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_pgx_gene ON silver.pharmacogenomics(gene_symbol);
CREATE INDEX IF NOT EXISTS idx_silver_pgx_variant ON silver.pharmacogenomics(variant_id);
CREATE INDEX IF NOT EXISTS idx_silver_pgx_evidence ON silver.pharmacogenomics(level_of_evidence);

-- Silver Bioactivity Table — already created in 040_silver_layer_tables.sql
-- Add columns that 040 may not include (idempotent ALTER)
DO $$
BEGIN
    ALTER TABLE silver.bioactivity ADD COLUMN IF NOT EXISTS target_id UUID;
    ALTER TABLE silver.bioactivity ADD COLUMN IF NOT EXISTS source_id VARCHAR(100);
    ALTER TABLE silver.bioactivity ADD COLUMN IF NOT EXISTS pmid VARCHAR(20);
    ALTER TABLE silver.bioactivity ADD COLUMN IF NOT EXISTS doi VARCHAR(200);
    ALTER TABLE silver.bioactivity ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
EXCEPTION WHEN undefined_table THEN
    NULL;  -- table does not exist yet, 040 will create it
END $$;

CREATE INDEX IF NOT EXISTS idx_silver_bioact_molecule ON silver.bioactivity(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_bioact_type ON silver.bioactivity(activity_type);

-- ============================================================================
-- STEP 5: PIPELINE JOBS TABLE FOR LINKING HISTORY
-- ============================================================================

-- Track pipeline and linking job history for scheduling persistence
CREATE TABLE IF NOT EXISTS raw.pipeline_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type VARCHAR(50) NOT NULL,  -- daily_linking, weekly_linking, daily, weekly, monthly
    status VARCHAR(20) NOT NULL,     -- running, completed, partial, failed
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_seconds NUMERIC(10,2),

    -- Linking-specific metrics
    molecules_processed INTEGER DEFAULT 0,
    identifiers_linked INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,

    -- General metrics
    records_processed INTEGER DEFAULT 0,
    records_created INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,

    -- Error tracking
    error_message TEXT,
    error_details JSONB,

    -- Metadata
    sources_included JSONB,
    job_metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_type ON raw.pipeline_jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status ON raw.pipeline_jobs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_completed ON raw.pipeline_jobs(completed_at);
CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_type_completed ON raw.pipeline_jobs(job_type, completed_at);

-- ============================================================================
-- STEP 6: LOG MIGRATION
-- ============================================================================

INSERT INTO public.pharma_predictor_db (key, value, description)
VALUES ('medallion_migration_050', NOW()::text, 'Complete medallion architecture with all 16 data sources')
ON CONFLICT (key) DO UPDATE SET value = NOW()::text, updated_at = NOW();

COMMIT;
