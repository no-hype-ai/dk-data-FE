-- Migration: 031_silver_tables.sql
-- Description: Create Silver layer tables for normalized, entity-resolved data
-- Date: 2026-01-23
-- Part of: 012-dk-data-platform

-- ==========================================
-- Core Molecule Table (Canonical Master)
-- ==========================================

CREATE TABLE IF NOT EXISTS silver_molecules (
    molecule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Canonical Identifiers (structure-based)
    inchi_key VARCHAR(27) UNIQUE, -- Master identifier for small molecules
    inchi TEXT,
    canonical_smiles TEXT,

    -- Molecule Type
    molecule_type VARCHAR(30) NOT NULL DEFAULT 'small_molecule'
        CHECK (molecule_type IN ('small_molecule', 'biologic', 'peptide', 'antibody', 'gene_therapy', 'cell_therapy', 'vaccine', 'unknown')),

    -- Primary Name
    preferred_name VARCHAR(500),
    inn_name VARCHAR(200), -- International Nonproprietary Name

    -- Molecular Properties (for small molecules)
    molecular_weight DECIMAL,
    molecular_formula VARCHAR(100),

    -- Data Quality
    data_quality_score DECIMAL, -- 0-1 completeness score
    last_quality_check TIMESTAMPTZ,

    -- Source Tracking
    primary_source VARCHAR(50),
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- For biologics without InChI Key
    fallback_identifier VARCHAR(100), -- DrugBank ID or UniProt ID
    fallback_identifier_type VARCHAR(30),

    CONSTRAINT inchi_or_fallback CHECK (
        inchi_key IS NOT NULL OR fallback_identifier IS NOT NULL
    )
);

CREATE INDEX idx_silver_mol_inchi ON silver_molecules(inchi_key) WHERE inchi_key IS NOT NULL;
CREATE INDEX idx_silver_mol_name ON silver_molecules(preferred_name);
CREATE INDEX idx_silver_mol_type ON silver_molecules(molecule_type);
CREATE INDEX idx_silver_mol_fallback ON silver_molecules(fallback_identifier) WHERE fallback_identifier IS NOT NULL;

-- ==========================================
-- Identifier Cross-Reference Mappings
-- ==========================================

CREATE TABLE IF NOT EXISTS silver_identifier_mappings (
    mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- The canonical molecule reference
    molecule_id UUID NOT NULL REFERENCES silver_molecules(molecule_id) ON DELETE CASCADE,

    -- Identifier being mapped
    identifier_type VARCHAR(30) NOT NULL,
    identifier_value VARCHAR(500) NOT NULL,

    -- Provenance
    source VARCHAR(50) NOT NULL,
    confidence DECIMAL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),

    -- Validation
    is_primary BOOLEAN DEFAULT FALSE,
    is_validated BOOLEAN DEFAULT FALSE,
    validated_at TIMESTAMPTZ,
    validated_by VARCHAR(100),

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE(molecule_id, identifier_type, identifier_value)
);

CREATE INDEX idx_mapping_type_value ON silver_identifier_mappings(identifier_type, identifier_value);
CREATE INDEX idx_mapping_molecule ON silver_identifier_mappings(molecule_id);
CREATE INDEX idx_mapping_low_confidence ON silver_identifier_mappings(confidence) WHERE confidence < 0.8;

-- ==========================================
-- Molecule Name Aliases (for fuzzy matching)
-- ==========================================

CREATE TABLE IF NOT EXISTS silver_molecule_aliases (
    alias_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    molecule_id UUID NOT NULL REFERENCES silver_molecules(molecule_id) ON DELETE CASCADE,

    -- Alias information
    alias_name VARCHAR(500) NOT NULL,
    alias_type VARCHAR(30) NOT NULL
        CHECK (alias_type IN ('brand_name', 'generic_name', 'inn', 'synonym', 'trade_name', 'code_name', 'chemical_name')),

    -- Context
    region VARCHAR(50),
    language VARCHAR(10) DEFAULT 'en',

    -- Source
    source VARCHAR(50) NOT NULL,

    -- Search optimization (for pg_trgm)
    alias_name_normalized VARCHAR(500),

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(molecule_id, alias_name, alias_type)
);

-- Trigram index for fuzzy matching (requires pg_trgm extension)
CREATE INDEX idx_alias_name_normalized ON silver_molecule_aliases(alias_name_normalized);
CREATE INDEX idx_alias_molecule ON silver_molecule_aliases(molecule_id);

-- ==========================================
-- Clinical Trials (Normalized)
-- ==========================================

CREATE TABLE IF NOT EXISTS silver_clinical_trials (
    trial_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- External Identifiers
    nct_id VARCHAR(20) UNIQUE,
    eudract_id VARCHAR(20),
    isrctn_id VARCHAR(20),

    -- Linked Molecule
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Trial Details
    title TEXT,
    brief_summary TEXT,
    detailed_description TEXT,

    -- Phase & Status
    phase VARCHAR(20),
    overall_status VARCHAR(50),
    start_date DATE,
    completion_date DATE,
    primary_completion_date DATE,

    -- Indications
    conditions JSONB, -- Array of condition names
    conditions_mesh JSONB, -- Array of MeSH terms

    -- Interventions
    interventions JSONB, -- Array of intervention objects

    -- Study Design
    study_type VARCHAR(50),
    allocation VARCHAR(50),
    intervention_model VARCHAR(50),
    masking VARCHAR(50),
    enrollment INTEGER,

    -- Sponsors
    lead_sponsor VARCHAR(500),
    collaborators JSONB,

    -- Outcomes
    primary_outcomes JSONB,
    secondary_outcomes JSONB,

    -- Results
    has_results BOOLEAN DEFAULT FALSE,
    results_first_posted DATE,

    -- Source Tracking
    bronze_id UUID,
    source VARCHAR(50) DEFAULT 'clinicaltrials_gov',
    source_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_silver_ct_molecule ON silver_clinical_trials(molecule_id);
CREATE INDEX idx_silver_ct_nct ON silver_clinical_trials(nct_id);
CREATE INDEX idx_silver_ct_phase ON silver_clinical_trials(phase);
CREATE INDEX idx_silver_ct_status ON silver_clinical_trials(overall_status);

-- ==========================================
-- Drug Labels (FDA/EMA)
-- ==========================================

CREATE TABLE IF NOT EXISTS silver_drug_labels (
    label_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Linked Molecule
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Identifiers
    set_id VARCHAR(100),
    spl_id VARCHAR(100),
    application_number VARCHAR(50),

    -- Product Info
    brand_name VARCHAR(500),
    generic_name VARCHAR(500),
    manufacturer VARCHAR(500),

    -- Label Sections
    indications_and_usage TEXT,
    dosage_and_administration TEXT,
    contraindications TEXT,
    warnings_and_precautions TEXT,
    adverse_reactions TEXT,
    drug_interactions TEXT,
    boxed_warning TEXT,

    -- Regulatory
    marketing_status VARCHAR(50),
    effective_date DATE,

    -- Source Tracking
    bronze_id UUID,
    source VARCHAR(50) DEFAULT 'openfda',
    source_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_silver_labels_molecule ON silver_drug_labels(molecule_id);
CREATE INDEX idx_silver_labels_brand ON silver_drug_labels(brand_name);

-- ==========================================
-- Adverse Events (FAERS)
-- ==========================================

CREATE TABLE IF NOT EXISTS silver_adverse_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Linked Molecule
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Report Info
    report_id VARCHAR(50),
    report_date DATE,
    receive_date DATE,

    -- Patient
    patient_age DECIMAL,
    patient_age_unit VARCHAR(10),
    patient_sex VARCHAR(10),
    patient_weight DECIMAL,

    -- Reactions
    reactions JSONB, -- Array of {name, outcome, severity}

    -- Drug Info
    drug_characterization VARCHAR(50), -- primary suspect, concomitant, etc.
    route_of_administration VARCHAR(100),
    dose_amount DECIMAL,
    dose_unit VARCHAR(50),

    -- Outcome
    serious BOOLEAN,
    serious_reasons JSONB, -- death, hospitalization, etc.

    -- Source Tracking
    bronze_id UUID,
    source VARCHAR(50) DEFAULT 'openfda_faers',
    source_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_silver_ae_molecule ON silver_adverse_events(molecule_id);
CREATE INDEX idx_silver_ae_serious ON silver_adverse_events(serious) WHERE serious = TRUE;
CREATE INDEX idx_silver_ae_date ON silver_adverse_events(report_date);

-- ==========================================
-- Patents
-- ==========================================

CREATE TABLE IF NOT EXISTS silver_patents (
    patent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Linked Molecule
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Patent Info
    patent_number VARCHAR(50) NOT NULL,
    patent_type VARCHAR(50), -- compound, formulation, method of use, etc.
    patent_country VARCHAR(10) DEFAULT 'US',

    -- Dates
    filing_date DATE,
    grant_date DATE,
    expiration_date DATE,

    -- Orange Book specific
    application_number VARCHAR(50),
    product_number VARCHAR(50),

    -- Claims
    claims_summary TEXT,

    -- Source Tracking
    bronze_id UUID,
    source VARCHAR(50),
    source_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_silver_patents_molecule ON silver_patents(molecule_id);
CREATE INDEX idx_silver_patents_expiration ON silver_patents(expiration_date);
CREATE INDEX idx_silver_patents_number ON silver_patents(patent_number);

-- ==========================================
-- Bioactivity Data (ChEMBL)
-- ==========================================

CREATE TABLE IF NOT EXISTS silver_bioactivity (
    activity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Linked Molecule
    molecule_id UUID REFERENCES silver_molecules(molecule_id),

    -- Target
    target_chembl_id VARCHAR(50),
    target_name VARCHAR(500),
    target_type VARCHAR(50),
    target_organism VARCHAR(100),

    -- Activity
    activity_type VARCHAR(50), -- IC50, Ki, EC50, etc.
    activity_value DECIMAL,
    activity_unit VARCHAR(50),
    activity_relation VARCHAR(10), -- =, <, >, etc.

    -- Assay
    assay_chembl_id VARCHAR(50),
    assay_type VARCHAR(50),
    assay_description TEXT,

    -- Source Tracking
    bronze_id UUID,
    source VARCHAR(50) DEFAULT 'chembl',
    source_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_silver_bio_molecule ON silver_bioactivity(molecule_id);
CREATE INDEX idx_silver_bio_target ON silver_bioactivity(target_chembl_id);
CREATE INDEX idx_silver_bio_activity ON silver_bioactivity(activity_type);

-- ==========================================
-- Transformation Run Log
-- ==========================================

CREATE TABLE IF NOT EXISTS silver_transformation_runs (
    id SERIAL PRIMARY KEY,
    source_table VARCHAR(100) NOT NULL,

    -- Run details
    run_id UUID DEFAULT gen_random_uuid(),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'partial')),

    -- Metrics
    records_input INTEGER DEFAULT 0,
    records_output INTEGER DEFAULT 0,
    records_deduplicated INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,

    -- Errors
    error_details JSONB,

    -- Bronze references processed
    bronze_ids_processed JSONB
);

CREATE INDEX idx_transform_runs_source ON silver_transformation_runs(source_table);
CREATE INDEX idx_transform_runs_status ON silver_transformation_runs(status);
