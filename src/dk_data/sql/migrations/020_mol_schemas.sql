-- Migration: 020_mol_schemas.sql
-- Feature: 012-dk-data-platform
-- Description: Create molecule data platform schemas and tables
-- Date: 2026-01-27

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

-- Vector similarity for future ML embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Trigram similarity for fuzzy text matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- =============================================================================
-- SCHEMA CREATION
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS mol_raw;
CREATE SCHEMA IF NOT EXISTS mol_bronze;
CREATE SCHEMA IF NOT EXISTS mol_silver;
CREATE SCHEMA IF NOT EXISTS mol_gold;
CREATE SCHEMA IF NOT EXISTS mol_app;
CREATE SCHEMA IF NOT EXISTS mol_api;

-- =============================================================================
-- MOL_RAW SCHEMA - Unmodified API Response Archive
-- Purpose: Store complete HTTP responses from external data sources
-- =============================================================================

-- Generic raw table template for all sources
-- Each source gets its own table following this pattern

CREATE TABLE IF NOT EXISTS mol_raw.clinicaltrials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'clinicaltrials'
);

CREATE TABLE IF NOT EXISTS mol_raw.openfda_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'openfda_labels'
);

CREATE TABLE IF NOT EXISTS mol_raw.openfda_faers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'openfda_faers'
);

CREATE TABLE IF NOT EXISTS mol_raw.chembl (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'chembl'
);

CREATE TABLE IF NOT EXISTS mol_raw.drugbank (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

CREATE TABLE IF NOT EXISTS mol_raw.pubchem (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

CREATE TABLE IF NOT EXISTS mol_raw.uniprot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

CREATE TABLE IF NOT EXISTS mol_raw.sider (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
    source_id VARCHAR(50) NOT NULL DEFAULT 'sider'
);

CREATE TABLE IF NOT EXISTS mol_raw.openalex (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- Indexes for raw tables
CREATE INDEX IF NOT EXISTS idx_raw_ct_request_id ON mol_raw.clinicaltrials(request_id);
CREATE INDEX IF NOT EXISTS idx_raw_ct_processed ON mol_raw.clinicaltrials(processed_to_bronze) WHERE processed_to_bronze = FALSE;
CREATE INDEX IF NOT EXISTS idx_raw_ct_hash ON mol_raw.clinicaltrials(response_body_hash);

CREATE INDEX IF NOT EXISTS idx_raw_fda_labels_processed ON mol_raw.openfda_labels(processed_to_bronze) WHERE processed_to_bronze = FALSE;
CREATE INDEX IF NOT EXISTS idx_raw_fda_faers_processed ON mol_raw.openfda_faers(processed_to_bronze) WHERE processed_to_bronze = FALSE;
CREATE INDEX IF NOT EXISTS idx_raw_chembl_processed ON mol_raw.chembl(processed_to_bronze) WHERE processed_to_bronze = FALSE;
CREATE INDEX IF NOT EXISTS idx_raw_pubchem_processed ON mol_raw.pubchem(processed_to_bronze) WHERE processed_to_bronze = FALSE;

-- =============================================================================
-- MOL_BRONZE SCHEMA - Parsed Source-Native Data
-- Purpose: Typed columns extracted from raw JSON responses
-- =============================================================================

CREATE TABLE IF NOT EXISTS mol_bronze.clinicaltrials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID REFERENCES mol_raw.clinicaltrials(id),
    nct_id VARCHAR(15) NOT NULL UNIQUE,
    brief_title TEXT,
    official_title TEXT,
    overall_status VARCHAR(50),
    phase VARCHAR(20),
    study_type VARCHAR(50),
    lead_sponsor_name VARCHAR(500),
    lead_sponsor_class VARCHAR(50),
    enrollment_count INTEGER,
    enrollment_type VARCHAR(20),
    start_date DATE,
    start_date_type VARCHAR(20),
    completion_date DATE,
    completion_date_type VARCHAR(20),
    primary_completion_date DATE,
    interventions JSONB,
    conditions JSONB,
    locations JSONB,
    record_hash VARCHAR(64),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mol_bronze.openfda_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID REFERENCES mol_raw.openfda_labels(id),
    set_id VARCHAR(50) NOT NULL UNIQUE,
    spl_id VARCHAR(50),
    application_number VARCHAR(20),
    brand_name VARCHAR(500),
    generic_name VARCHAR(500),
    manufacturer_name VARCHAR(500),
    product_type VARCHAR(100),
    route TEXT[],
    substance_name TEXT[],
    active_ingredient JSONB,
    indications_and_usage TEXT,
    contraindications TEXT,
    warnings TEXT,
    boxed_warning TEXT,
    adverse_reactions TEXT,
    drug_interactions TEXT,
    effective_time DATE,
    record_hash VARCHAR(64),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mol_bronze.openfda_faers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID REFERENCES mol_raw.openfda_faers(id),
    safety_report_id VARCHAR(100) NOT NULL,
    receive_date DATE,
    receipt_date DATE,
    serious INTEGER,
    serious_death INTEGER,
    serious_hospitalization INTEGER,
    serious_lifethreatening INTEGER,
    serious_disability INTEGER,
    patient_age DECIMAL(10,2),
    patient_age_unit VARCHAR(20),
    patient_sex VARCHAR(10),
    patient_weight DECIMAL(10,2),
    drugs JSONB,
    reactions JSONB,
    outcomes JSONB,
    reporter_country VARCHAR(50),
    record_hash VARCHAR(64),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mol_bronze.chembl (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID REFERENCES mol_raw.chembl(id),
    chembl_id VARCHAR(30) NOT NULL UNIQUE,
    molecule_type VARCHAR(50),
    pref_name VARCHAR(500),
    max_phase INTEGER,
    therapeutic_flag BOOLEAN,
    dosed_ingredient BOOLEAN,
    structure_type VARCHAR(20),
    inchi_key VARCHAR(27),
    inchi TEXT,
    canonical_smiles TEXT,
    molecular_formula VARCHAR(200),
    molecular_weight DECIMAL(12,4),
    atc_classifications TEXT[],
    indication_class TEXT,
    usan_stem VARCHAR(100),
    usan_year INTEGER,
    first_approval INTEGER,
    oral BOOLEAN,
    parenteral BOOLEAN,
    topical BOOLEAN,
    black_box_warning BOOLEAN,
    prodrug BOOLEAN,
    record_hash VARCHAR(64),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mol_bronze.drugbank (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID REFERENCES mol_raw.drugbank(id),
    drugbank_id VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(500),
    drug_type VARCHAR(50),
    cas_number VARCHAR(20),
    unii VARCHAR(20),
    inchi_key VARCHAR(27),
    inchi TEXT,
    smiles TEXT,
    molecular_formula VARCHAR(200),
    average_mass DECIMAL(12,4),
    monoisotopic_mass DECIMAL(12,4),
    state VARCHAR(20),
    indication TEXT,
    pharmacodynamics TEXT,
    mechanism_of_action TEXT,
    toxicity TEXT,
    metabolism TEXT,
    half_life TEXT,
    protein_binding TEXT,
    food_interactions JSONB,
    drug_interactions JSONB,
    categories JSONB,
    atc_codes TEXT[],
    patents JSONB,
    record_hash VARCHAR(64),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mol_bronze.pubchem (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID REFERENCES mol_raw.pubchem(id),
    cid BIGINT NOT NULL UNIQUE,
    iupac_name TEXT,
    molecular_formula VARCHAR(200),
    molecular_weight DECIMAL(12,4),
    canonical_smiles TEXT,
    isomeric_smiles TEXT,
    inchi TEXT,
    inchi_key VARCHAR(27),
    xlogp DECIMAL(10,4),
    exact_mass DECIMAL(12,4),
    monoisotopic_mass DECIMAL(12,4),
    tpsa DECIMAL(10,4),
    complexity INTEGER,
    charge INTEGER,
    h_bond_donor_count INTEGER,
    h_bond_acceptor_count INTEGER,
    rotatable_bond_count INTEGER,
    heavy_atom_count INTEGER,
    synonyms TEXT[],
    record_hash VARCHAR(64),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mol_bronze.sider (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_id UUID REFERENCES mol_raw.sider(id),
    stitch_id_flat VARCHAR(20) NOT NULL,
    stitch_id_stereo VARCHAR(20),
    drug_name VARCHAR(500),
    meddra_concept_id VARCHAR(20),
    meddra_concept_name VARCHAR(500),
    side_effect_name VARCHAR(500),
    frequency VARCHAR(50),
    frequency_lower DECIMAL(8,6),
    frequency_upper DECIMAL(8,6),
    record_hash VARCHAR(64),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_to_silver BOOLEAN DEFAULT FALSE
);

-- Indexes for bronze tables
CREATE INDEX IF NOT EXISTS idx_bronze_ct_nct ON mol_bronze.clinicaltrials(nct_id);
CREATE INDEX IF NOT EXISTS idx_bronze_ct_status ON mol_bronze.clinicaltrials(overall_status);
CREATE INDEX IF NOT EXISTS idx_bronze_ct_processed ON mol_bronze.clinicaltrials(processed_to_silver) WHERE processed_to_silver = FALSE;

CREATE INDEX IF NOT EXISTS idx_bronze_chembl_id ON mol_bronze.chembl(chembl_id);
CREATE INDEX IF NOT EXISTS idx_bronze_chembl_inchi ON mol_bronze.chembl(inchi_key);
CREATE INDEX IF NOT EXISTS idx_bronze_chembl_processed ON mol_bronze.chembl(processed_to_silver) WHERE processed_to_silver = FALSE;

CREATE INDEX IF NOT EXISTS idx_bronze_drugbank_id ON mol_bronze.drugbank(drugbank_id);
CREATE INDEX IF NOT EXISTS idx_bronze_drugbank_inchi ON mol_bronze.drugbank(inchi_key);
CREATE INDEX IF NOT EXISTS idx_bronze_drugbank_processed ON mol_bronze.drugbank(processed_to_silver) WHERE processed_to_silver = FALSE;

CREATE INDEX IF NOT EXISTS idx_bronze_pubchem_cid ON mol_bronze.pubchem(cid);
CREATE INDEX IF NOT EXISTS idx_bronze_pubchem_inchi ON mol_bronze.pubchem(inchi_key);
CREATE INDEX IF NOT EXISTS idx_bronze_pubchem_processed ON mol_bronze.pubchem(processed_to_silver) WHERE processed_to_silver = FALSE;

CREATE INDEX IF NOT EXISTS idx_bronze_labels_set_id ON mol_bronze.openfda_labels(set_id);
CREATE INDEX IF NOT EXISTS idx_bronze_labels_processed ON mol_bronze.openfda_labels(processed_to_silver) WHERE processed_to_silver = FALSE;

-- =============================================================================
-- MOL_SILVER SCHEMA - Entity-Resolved Normalized Data
-- Purpose: Cross-source resolved entities with canonical identifiers
-- =============================================================================

CREATE TABLE IF NOT EXISTS mol_silver.molecules (
    molecule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inchi_key VARCHAR(27) UNIQUE NOT NULL,
    chembl_id VARCHAR(30),
    drugbank_id VARCHAR(20),
    pubchem_cid BIGINT,
    rxnorm_cui VARCHAR(20),
    unii VARCHAR(20),
    cas_number VARCHAR(20),
    canonical_name VARCHAR(500),
    brand_names TEXT[],
    generic_names TEXT[],
    smiles TEXT,
    inchi TEXT,
    molecular_formula VARCHAR(200),
    molecular_weight DECIMAL(12,4),
    molecule_type VARCHAR(50),
    therapeutic_areas TEXT[],
    atc_codes TEXT[],
    needs_review BOOLEAN DEFAULT FALSE,
    review_reason TEXT,
    resolution_confidence DECIMAL(3,2) DEFAULT 1.0,
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_count INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mol_silver.identifier_mappings (
    mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID NOT NULL REFERENCES mol_silver.molecules(molecule_id) ON DELETE CASCADE,
    identifier_type VARCHAR(30) NOT NULL,
    identifier_value VARCHAR(500) NOT NULL,
    source VARCHAR(50) NOT NULL,
    confidence DECIMAL(3,2) DEFAULT 1.0,
    is_primary BOOLEAN DEFAULT FALSE,
    is_validated BOOLEAN DEFAULT FALSE,
    validated_at TIMESTAMPTZ,
    validated_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(molecule_id, identifier_type, identifier_value)
);

CREATE TABLE IF NOT EXISTS mol_silver.molecule_aliases (
    alias_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID NOT NULL REFERENCES mol_silver.molecules(molecule_id) ON DELETE CASCADE,
    alias_name VARCHAR(500) NOT NULL,
    alias_type VARCHAR(30) NOT NULL,
    region VARCHAR(50),
    language VARCHAR(10),
    source VARCHAR(50) NOT NULL,
    alias_name_normalized VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_silver.clinical_trials (
    trial_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nct_id VARCHAR(20) UNIQUE NOT NULL,
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    title TEXT,
    brief_summary TEXT,
    phase VARCHAR(20),
    status VARCHAR(50),
    study_type VARCHAR(50),
    conditions TEXT[],
    intervention_names TEXT[],
    enrollment_target INTEGER,
    enrollment_actual INTEGER,
    start_date DATE,
    completion_date DATE,
    sponsor VARCHAR(500),
    sponsor_type VARCHAR(50),
    has_results BOOLEAN DEFAULT FALSE,
    outcome_type VARCHAR(50),
    bronze_source_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_silver.drug_labels (
    label_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id VARCHAR(50) UNIQUE NOT NULL,
    spl_id VARCHAR(50),
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    brand_name VARCHAR(500),
    generic_name VARCHAR(500),
    manufacturer VARCHAR(500),
    application_number VARCHAR(20),
    approval_date DATE,
    marketing_status VARCHAR(50),
    route_of_administration TEXT[],
    dosage_forms TEXT[],
    indications TEXT,
    contraindications TEXT,
    warnings TEXT,
    boxed_warning TEXT,
    adverse_reactions TEXT,
    drug_interactions TEXT,
    effective_date DATE,
    bronze_source_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_silver.adverse_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(20) NOT NULL,
    source_report_id VARCHAR(100),
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    drug_name_reported VARCHAR(500),
    reaction_meddra_pt VARCHAR(500),
    reaction_meddra_code VARCHAR(20),
    seriousness VARCHAR(50),
    outcome VARCHAR(50),
    patient_age INTEGER,
    patient_sex VARCHAR(10),
    report_date DATE,
    country VARCHAR(50),
    bronze_source_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_silver.bioactivity (
    bioactivity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID NOT NULL REFERENCES mol_silver.molecules(molecule_id),
    target_id VARCHAR(50),
    target_name VARCHAR(500),
    target_type VARCHAR(50),
    activity_type VARCHAR(50),
    activity_value DECIMAL(20,6),
    activity_unit VARCHAR(50),
    assay_description TEXT,
    source VARCHAR(50),
    source_id VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for silver tables
CREATE INDEX IF NOT EXISTS idx_silver_mol_inchi ON mol_silver.molecules(inchi_key);
CREATE INDEX IF NOT EXISTS idx_silver_mol_chembl ON mol_silver.molecules(chembl_id);
CREATE INDEX IF NOT EXISTS idx_silver_mol_drugbank ON mol_silver.molecules(drugbank_id);
CREATE INDEX IF NOT EXISTS idx_silver_mol_pubchem ON mol_silver.molecules(pubchem_cid);
CREATE INDEX IF NOT EXISTS idx_silver_mol_name ON mol_silver.molecules(canonical_name);
CREATE INDEX IF NOT EXISTS idx_silver_mol_review ON mol_silver.molecules(needs_review) WHERE needs_review = TRUE;

CREATE INDEX IF NOT EXISTS idx_silver_idmap_molecule ON mol_silver.identifier_mappings(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_idmap_type_value ON mol_silver.identifier_mappings(identifier_type, identifier_value);

-- Trigram index for fuzzy name matching
CREATE INDEX IF NOT EXISTS idx_silver_aliases_normalized ON mol_silver.molecule_aliases USING GIN (alias_name_normalized gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_silver_aliases_molecule ON mol_silver.molecule_aliases(molecule_id);

CREATE INDEX IF NOT EXISTS idx_silver_trials_nct ON mol_silver.clinical_trials(nct_id);
CREATE INDEX IF NOT EXISTS idx_silver_trials_molecule ON mol_silver.clinical_trials(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_trials_phase ON mol_silver.clinical_trials(phase);
CREATE INDEX IF NOT EXISTS idx_silver_trials_status ON mol_silver.clinical_trials(status);

CREATE INDEX IF NOT EXISTS idx_silver_labels_set ON mol_silver.drug_labels(set_id);
CREATE INDEX IF NOT EXISTS idx_silver_labels_molecule ON mol_silver.drug_labels(molecule_id);

CREATE INDEX IF NOT EXISTS idx_silver_ae_molecule ON mol_silver.adverse_events(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_ae_reaction ON mol_silver.adverse_events(reaction_meddra_pt);
CREATE INDEX IF NOT EXISTS idx_silver_ae_source ON mol_silver.adverse_events(source);

-- =============================================================================
-- MOL_GOLD SCHEMA - Aggregated Decision-Ready Views
-- Purpose: Pre-computed aggregates and metrics for analytics
-- =============================================================================

CREATE TABLE IF NOT EXISTS mol_gold.molecule_profiles (
    profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID UNIQUE NOT NULL REFERENCES mol_silver.molecules(molecule_id),
    inchi_key VARCHAR(27) NOT NULL,
    canonical_name VARCHAR(500),
    lifecycle_stage VARCHAR(50),
    stage_confidence DECIMAL(3,2),
    data_completeness DECIMAL(3,2),
    trial_count INTEGER DEFAULT 0,
    active_trial_count INTEGER DEFAULT 0,
    label_count INTEGER DEFAULT 0,
    indication_count INTEGER DEFAULT 0,
    adverse_event_count INTEGER DEFAULT 0,
    serious_ae_count INTEGER DEFAULT 0,
    publication_count INTEGER DEFAULT 0,
    patent_expiry_date DATE,
    first_approval_date DATE,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_gold.safety_signals (
    signal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID NOT NULL REFERENCES mol_silver.molecules(molecule_id),
    reaction_meddra_pt VARCHAR(500) NOT NULL,
    reaction_soc VARCHAR(200),
    case_count INTEGER NOT NULL DEFAULT 0,
    prr_score DECIMAL(8,4),
    ror_score DECIMAL(8,4),
    ic_score DECIMAL(8,4),
    signal_strength VARCHAR(20),
    first_reported DATE,
    last_reported DATE,
    trend_direction VARCHAR(20),
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(molecule_id, reaction_meddra_pt)
);

CREATE TABLE IF NOT EXISTS mol_gold.competitive_landscape (
    landscape_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    indication VARCHAR(500) NOT NULL,
    indication_mesh_id VARCHAR(20),
    molecule_ids UUID[],
    approved_count INTEGER DEFAULT 0,
    phase3_count INTEGER DEFAULT 0,
    phase2_count INTEGER DEFAULT 0,
    phase1_count INTEGER DEFAULT 0,
    market_leaders JSONB,
    recent_approvals JSONB,
    pipeline_trends JSONB,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_gold.lifecycle_stages (
    stage_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id UUID NOT NULL REFERENCES mol_silver.molecules(molecule_id),
    indication VARCHAR(500),
    lifecycle_stage VARCHAR(50) NOT NULL,
    confidence DECIMAL(3,2),
    evidence_sources TEXT[],
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validated_by VARCHAR(100),
    validated_at TIMESTAMPTZ,
    UNIQUE(molecule_id, indication)
);

-- Indexes for gold tables
CREATE INDEX IF NOT EXISTS idx_gold_profiles_molecule ON mol_gold.molecule_profiles(molecule_id);
CREATE INDEX IF NOT EXISTS idx_gold_profiles_stage ON mol_gold.molecule_profiles(lifecycle_stage);
CREATE INDEX IF NOT EXISTS idx_gold_signals_molecule ON mol_gold.safety_signals(molecule_id);
CREATE INDEX IF NOT EXISTS idx_gold_signals_reaction ON mol_gold.safety_signals(reaction_meddra_pt);
CREATE INDEX IF NOT EXISTS idx_gold_landscape_indication ON mol_gold.competitive_landscape(indication);

-- =============================================================================
-- MOL_APP SCHEMA - Application Layer (User Features)
-- Purpose: User-specific tracking, annotations, and alerts
-- =============================================================================

CREATE TABLE IF NOT EXISTS mol_app.user_tracked_molecules (
    tracking_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    molecule_id UUID NOT NULL REFERENCES mol_silver.molecules(molecule_id),
    indication VARCHAR(500),
    lifecycle_stage VARCHAR(50),
    stage_validated BOOLEAN DEFAULT FALSE,
    validation_date TIMESTAMPTZ,
    notes TEXT,
    priority VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, molecule_id, indication)
);

CREATE TABLE IF NOT EXISTS mol_app.user_annotations (
    annotation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    molecule_id UUID NOT NULL REFERENCES mol_silver.molecules(molecule_id),
    tracking_id UUID REFERENCES mol_app.user_tracked_molecules(tracking_id),
    annotation_type VARCHAR(50) NOT NULL,
    title VARCHAR(500),
    content TEXT,
    source_url VARCHAR(1000),
    is_private BOOLEAN DEFAULT FALSE,
    lifecycle_stage VARCHAR(50),
    evidence_strength VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mol_app.alert_configs (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    alert_type VARCHAR(50) NOT NULL,
    threshold JSONB,
    channels TEXT[],
    is_active BOOLEAN DEFAULT TRUE,
    last_triggered TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, molecule_id, alert_type)
);

CREATE TABLE IF NOT EXISTS mol_app.alert_history (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_id UUID NOT NULL REFERENCES mol_app.alert_configs(config_id),
    user_id UUID NOT NULL,
    molecule_id UUID REFERENCES mol_silver.molecules(molecule_id),
    alert_type VARCHAR(50) NOT NULL,
    alert_data JSONB,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS mol_app.onboarding_audit_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    molecule_id UUID,
    entity_type VARCHAR(50),
    entity_id UUID,
    old_values JSONB,
    new_values JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for app tables
CREATE INDEX IF NOT EXISTS idx_app_tracked_user ON mol_app.user_tracked_molecules(user_id);
CREATE INDEX IF NOT EXISTS idx_app_tracked_molecule ON mol_app.user_tracked_molecules(molecule_id);
CREATE INDEX IF NOT EXISTS idx_app_annotations_user ON mol_app.user_annotations(user_id);
CREATE INDEX IF NOT EXISTS idx_app_annotations_molecule ON mol_app.user_annotations(molecule_id);
CREATE INDEX IF NOT EXISTS idx_app_alerts_user ON mol_app.alert_configs(user_id);
CREATE INDEX IF NOT EXISTS idx_app_audit_user ON mol_app.onboarding_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_app_audit_created ON mol_app.onboarding_audit_log(created_at);

-- =============================================================================
-- ROW LEVEL SECURITY for Application Tables
-- =============================================================================

ALTER TABLE mol_app.user_tracked_molecules ENABLE ROW LEVEL SECURITY;
ALTER TABLE mol_app.user_annotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE mol_app.alert_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE mol_app.alert_history ENABLE ROW LEVEL SECURITY;

-- RLS policies will be created per-role below

-- =============================================================================
-- ROLES AND PERMISSIONS
-- =============================================================================

-- Create molecule platform roles
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_viewer') THEN
        CREATE ROLE mol_viewer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_analyst') THEN
        CREATE ROLE mol_analyst NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_data_ops') THEN
        CREATE ROLE mol_data_ops NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mol_admin') THEN
        CREATE ROLE mol_admin NOLOGIN;
    END IF;
END
$$;

-- Grant role hierarchy
GRANT mol_viewer TO mol_analyst;
GRANT mol_analyst TO mol_data_ops;
GRANT mol_data_ops TO mol_admin;

-- Grant to authenticator for role switching
GRANT mol_viewer TO authenticator;
GRANT mol_analyst TO authenticator;
GRANT mol_data_ops TO authenticator;
GRANT mol_admin TO authenticator;

-- Schema usage grants
GRANT USAGE ON SCHEMA mol_api TO mol_viewer;
GRANT USAGE ON SCHEMA mol_api TO mol_analyst;
GRANT USAGE ON SCHEMA mol_api TO mol_data_ops;
GRANT USAGE ON SCHEMA mol_api TO mol_admin;

GRANT USAGE ON SCHEMA mol_gold TO mol_viewer;
GRANT USAGE ON SCHEMA mol_gold TO mol_analyst;

GRANT USAGE ON SCHEMA mol_silver TO mol_analyst;
GRANT USAGE ON SCHEMA mol_silver TO mol_data_ops;

GRANT USAGE ON SCHEMA mol_bronze TO mol_data_ops;
GRANT USAGE ON SCHEMA mol_raw TO mol_data_ops;

GRANT USAGE ON SCHEMA mol_app TO mol_analyst;

-- Table-level permissions

-- mol_viewer: Read gold layer
GRANT SELECT ON ALL TABLES IN SCHEMA mol_gold TO mol_viewer;
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_gold GRANT SELECT ON TABLES TO mol_viewer;

-- mol_analyst: Read silver, write app layer
GRANT SELECT ON ALL TABLES IN SCHEMA mol_silver TO mol_analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_silver GRANT SELECT ON TABLES TO mol_analyst;

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA mol_app TO mol_analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_app GRANT SELECT, INSERT, UPDATE ON TABLES TO mol_analyst;

-- mol_data_ops: Read/write bronze, manage pipelines
GRANT SELECT ON ALL TABLES IN SCHEMA mol_raw TO mol_data_ops;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA mol_bronze TO mol_data_ops;
ALTER DEFAULT PRIVILEGES IN SCHEMA mol_bronze GRANT SELECT, INSERT, UPDATE ON TABLES TO mol_data_ops;

-- mol_admin: Full access
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_raw TO mol_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_bronze TO mol_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_silver TO mol_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_gold TO mol_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_app TO mol_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA mol_api TO mol_admin;

-- =============================================================================
-- RLS Policies
-- =============================================================================

-- Users can only see their own tracked molecules
CREATE POLICY user_tracked_molecules_isolation ON mol_app.user_tracked_molecules
    USING (user_id = COALESCE(
        NULLIF(current_setting('request.jwt.claims', true), '')::json->>'sub',
        current_setting('app.current_user_id', true)
    )::uuid);

-- Users can only see their own annotations (unless public)
CREATE POLICY user_annotations_isolation ON mol_app.user_annotations
    USING (
        user_id = COALESCE(
            NULLIF(current_setting('request.jwt.claims', true), '')::json->>'sub',
            current_setting('app.current_user_id', true)
        )::uuid
        OR is_private = FALSE
    );

-- Users can only see their own alert configs
CREATE POLICY alert_configs_isolation ON mol_app.alert_configs
    USING (user_id = COALESCE(
        NULLIF(current_setting('request.jwt.claims', true), '')::json->>'sub',
        current_setting('app.current_user_id', true)
    )::uuid);

-- Users can only see their own alert history
CREATE POLICY alert_history_isolation ON mol_app.alert_history
    USING (user_id = COALESCE(
        NULLIF(current_setting('request.jwt.claims', true), '')::json->>'sub',
        current_setting('app.current_user_id', true)
    )::uuid);

-- =============================================================================
-- COMPLETION MESSAGE
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Molecule platform schema migration complete (020_mol_schemas.sql)';
    RAISE NOTICE 'Schemas created: mol_raw, mol_bronze, mol_silver, mol_gold, mol_app, mol_api';
    RAISE NOTICE 'Extensions enabled: vector, pg_trgm';
    RAISE NOTICE 'Roles created: mol_viewer, mol_analyst, mol_data_ops, mol_admin';
    RAISE NOTICE 'RLS enabled on mol_app tables';
END
$$;
