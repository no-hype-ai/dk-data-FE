-- Migration 030: Silver Layer Tables
-- Purpose: Normalized, deduplicated entities with cross-source resolution
-- Part of DK Molecule Data Platform (012-dk-data-platform)

-- Create schema for silver layer
CREATE SCHEMA IF NOT EXISTS silver;

-- ============================================================================
-- SILVER LAYER: Entity Resolution & Normalized Data
-- ============================================================================

-- Core Molecule Table (Master Entity)
CREATE TABLE IF NOT EXISTS mol_silver.molecules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Canonical identifier (InChI Key for small molecules)
    inchi_key VARCHAR(27),

    -- Canonical name (highest precedence source)
    canonical_name VARCHAR(500),
    name_source VARCHAR(50),  -- Which source provided the canonical name

    -- Structure
    canonical_smiles TEXT,
    inchi TEXT,
    molecular_formula VARCHAR(200),
    molecular_weight NUMERIC(12,4),

    -- Classification
    molecule_type VARCHAR(50),  -- small_molecule, protein, antibody, peptide, etc.
    therapeutic_areas JSONB,
    mechanism_of_action TEXT,

    -- Development status
    development_status VARCHAR(50),  -- preclinical, phase_1, phase_2, phase_3, approved, withdrawn
    max_phase INTEGER,
    first_approval_year INTEGER,
    approval_date DATE,

    -- Data quality
    resolution_confidence NUMERIC(3,2) DEFAULT 1.0,
    needs_review BOOLEAN DEFAULT FALSE,  -- Quarantine flag for <0.8 confidence
    review_reason TEXT,

    -- Provenance
    data_sources JSONB,  -- Array of sources contributing to this record
    primary_source VARCHAR(50),  -- Highest precedence source

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(inchi_key)
);

CREATE INDEX IF NOT EXISTS idx_silver_mol_inchi ON mol_silver.molecules(inchi_key);
CREATE INDEX IF NOT EXISTS idx_silver_mol_name ON mol_silver.molecules(canonical_name);
CREATE INDEX IF NOT EXISTS idx_silver_mol_status ON mol_silver.molecules(development_status);
CREATE INDEX IF NOT EXISTS idx_silver_mol_needs_review ON mol_silver.molecules(needs_review) WHERE needs_review = TRUE;
CREATE INDEX IF NOT EXISTS idx_silver_mol_name_trgm ON mol_silver.molecules USING GIN(canonical_name gin_trgm_ops);

-- Identifier Mappings (Cross-Reference Table)
CREATE TABLE IF NOT EXISTS mol_silver.identifier_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- The canonical molecule reference
    molecule_id UUID REFERENCES mol_silver.molecules(id) ON DELETE CASCADE,

    -- Identifier being mapped
    identifier_type VARCHAR(30) NOT NULL,  -- inchi_key, chembl_id, drugbank_id, pubchem_cid, etc.
    identifier_value VARCHAR(500) NOT NULL,

    -- Provenance
    source VARCHAR(50) NOT NULL,  -- Which API/database provided this mapping
    confidence NUMERIC(3,2) DEFAULT 1.0,

    -- Validation
    is_primary BOOLEAN DEFAULT FALSE,  -- Is this the primary ID for this type?
    is_validated BOOLEAN DEFAULT FALSE,
    validated_at TIMESTAMPTZ,
    validated_by VARCHAR(100),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(molecule_id, identifier_type, identifier_value)
);

CREATE INDEX IF NOT EXISTS idx_silver_mapping_type_value ON mol_silver.identifier_mappings(identifier_type, identifier_value);
CREATE INDEX IF NOT EXISTS idx_silver_mapping_molecule ON mol_silver.identifier_mappings(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_mapping_source ON mol_silver.identifier_mappings(source);

-- Molecule Aliases (for fuzzy name resolution)
CREATE TABLE IF NOT EXISTS mol_silver.molecule_aliases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    molecule_id UUID REFERENCES mol_silver.molecules(id) ON DELETE CASCADE,

    -- Alias information
    alias_name VARCHAR(500) NOT NULL,
    alias_type VARCHAR(30) NOT NULL,  -- brand_name, generic_name, inn, synonym, trade_name, code_name
    alias_name_normalized VARCHAR(500),  -- Lowercase, no special chars

    -- Context
    region VARCHAR(50),  -- USA, EU, JP, etc.
    language VARCHAR(10) DEFAULT 'en',

    -- Source
    source VARCHAR(50) NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(molecule_id, alias_name, alias_type)
);

CREATE INDEX IF NOT EXISTS idx_silver_alias_name ON mol_silver.molecule_aliases(alias_name_normalized);
CREATE INDEX IF NOT EXISTS idx_silver_alias_molecule ON mol_silver.molecule_aliases(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_alias_name_trgm ON mol_silver.molecule_aliases USING GIN(alias_name_normalized gin_trgm_ops);

-- Clinical Trials (Normalized)
CREATE TABLE IF NOT EXISTS mol_silver.clinical_trials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Link to molecule
    molecule_id UUID REFERENCES mol_silver.molecules(id),

    -- Trial identifiers
    nct_id VARCHAR(15) NOT NULL,
    org_study_id VARCHAR(100),

    -- Basic info
    title TEXT,
    brief_summary TEXT,
    phase VARCHAR(20),
    study_type VARCHAR(50),
    status VARCHAR(50),

    -- Dates
    start_date DATE,
    completion_date DATE,
    primary_completion_date DATE,

    -- Sponsor
    sponsor VARCHAR(500),
    sponsor_type VARCHAR(50),
    collaborators JSONB,

    -- Design
    allocation VARCHAR(50),
    intervention_model VARCHAR(100),
    masking VARCHAR(100),
    enrollment INTEGER,

    -- Eligibility
    eligibility_criteria TEXT,
    minimum_age VARCHAR(20),
    maximum_age VARCHAR(20),
    sex VARCHAR(20),

    -- Conditions and Interventions
    conditions JSONB,
    interventions JSONB,
    primary_outcomes JSONB,
    secondary_outcomes JSONB,

    -- Locations
    locations JSONB,
    countries JSONB,

    -- Source
    source VARCHAR(50) DEFAULT 'clinicaltrials_gov',
    source_updated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(nct_id)
);

CREATE INDEX IF NOT EXISTS idx_silver_trial_nct ON mol_silver.clinical_trials(nct_id);
CREATE INDEX IF NOT EXISTS idx_silver_trial_molecule ON mol_silver.clinical_trials(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_trial_phase ON mol_silver.clinical_trials(phase);
CREATE INDEX IF NOT EXISTS idx_silver_trial_status ON mol_silver.clinical_trials(status);
CREATE INDEX IF NOT EXISTS idx_silver_trial_sponsor ON mol_silver.clinical_trials(sponsor);

-- Adverse Events (Aggregated from FAERS)
CREATE TABLE IF NOT EXISTS mol_silver.adverse_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    molecule_id UUID REFERENCES mol_silver.molecules(id),

    -- MedDRA coding
    meddra_pt VARCHAR(200),  -- Preferred term
    meddra_pt_code VARCHAR(20),
    meddra_soc VARCHAR(200),  -- System Organ Class
    meddra_soc_code VARCHAR(20),

    -- Counts
    report_count INTEGER DEFAULT 0,
    serious_count INTEGER DEFAULT 0,
    death_count INTEGER DEFAULT 0,
    hospitalization_count INTEGER DEFAULT 0,

    -- Rates (per 1000 reports)
    reporting_rate NUMERIC(10,4),
    prr NUMERIC(10,4),  -- Proportional Reporting Ratio
    ror NUMERIC(10,4),  -- Reporting Odds Ratio

    -- Time range of data
    first_report_date DATE,
    last_report_date DATE,

    -- Source
    source VARCHAR(50) DEFAULT 'openfda_faers',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(molecule_id, meddra_pt_code)
);

CREATE INDEX IF NOT EXISTS idx_silver_ae_molecule ON mol_silver.adverse_events(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_ae_meddra ON mol_silver.adverse_events(meddra_pt);
CREATE INDEX IF NOT EXISTS idx_silver_ae_soc ON mol_silver.adverse_events(meddra_soc);

-- Drug Labels (FDA Labels)
CREATE TABLE IF NOT EXISTS mol_silver.drug_labels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    molecule_id UUID REFERENCES mol_silver.molecules(id),

    -- Label identifiers
    set_id VARCHAR(50) NOT NULL,
    spl_id VARCHAR(50),
    version INTEGER,

    -- Product info
    brand_name TEXT,
    generic_name TEXT,
    manufacturer VARCHAR(500),
    application_number VARCHAR(20),
    product_type VARCHAR(100),

    -- Label sections (key ones)
    indications_and_usage TEXT,
    dosage_and_administration TEXT,
    contraindications TEXT,
    warnings TEXT,
    boxed_warning TEXT,
    adverse_reactions TEXT,
    drug_interactions TEXT,
    mechanism_of_action TEXT,

    -- Dates
    effective_date DATE,

    -- Source
    source VARCHAR(50) DEFAULT 'openfda_labels',
    source_updated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(set_id, version)
);

CREATE INDEX IF NOT EXISTS idx_silver_label_molecule ON mol_silver.drug_labels(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_label_set_id ON mol_silver.drug_labels(set_id);
CREATE INDEX IF NOT EXISTS idx_silver_label_brand ON mol_silver.drug_labels(brand_name);

-- Bioactivity (from ChEMBL)
CREATE TABLE IF NOT EXISTS mol_silver.bioactivity (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    molecule_id UUID REFERENCES mol_silver.molecules(id),

    -- Target info
    target_chembl_id VARCHAR(20),
    target_name VARCHAR(500),
    target_type VARCHAR(50),
    target_organism VARCHAR(200),

    -- Assay info
    assay_chembl_id VARCHAR(20),
    assay_type VARCHAR(50),
    assay_description TEXT,

    -- Activity
    activity_type VARCHAR(50),  -- IC50, Ki, EC50, etc.
    activity_value NUMERIC,
    activity_units VARCHAR(50),
    activity_relation VARCHAR(5),  -- =, <, >, etc.

    pchembl_value NUMERIC(5,2),

    -- Source
    source VARCHAR(50) DEFAULT 'chembl',
    source_updated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(molecule_id, target_chembl_id, assay_chembl_id, activity_type)
);

CREATE INDEX IF NOT EXISTS idx_silver_bio_molecule ON mol_silver.bioactivity(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_bio_target ON mol_silver.bioactivity(target_chembl_id);
CREATE INDEX IF NOT EXISTS idx_silver_bio_type ON mol_silver.bioactivity(activity_type);

-- Targets (from UniProt)
CREATE TABLE IF NOT EXISTS mol_silver.targets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Identifiers
    uniprot_id VARCHAR(15) NOT NULL,
    gene_symbol VARCHAR(50),
    protein_name TEXT,

    -- Organism
    organism VARCHAR(200),
    organism_id INTEGER,

    -- Function
    function_description TEXT,
    subcellular_location JSONB,

    -- Structure
    sequence TEXT,
    sequence_length INTEGER,

    -- Cross-references
    pdb_ids JSONB,
    chembl_id VARCHAR(20),

    -- Source
    source VARCHAR(50) DEFAULT 'uniprot',
    source_updated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(uniprot_id)
);

CREATE INDEX IF NOT EXISTS idx_silver_target_uniprot ON mol_silver.targets(uniprot_id);
CREATE INDEX IF NOT EXISTS idx_silver_target_gene ON mol_silver.targets(gene_symbol);

-- Molecule-Target Relationships
CREATE TABLE IF NOT EXISTS mol_silver.molecule_targets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    molecule_id UUID REFERENCES mol_silver.molecules(id) ON DELETE CASCADE,
    target_id UUID REFERENCES mol_silver.targets(id) ON DELETE CASCADE,

    -- Relationship type
    relationship_type VARCHAR(50),  -- target, enzyme, carrier, transporter
    action_type VARCHAR(50),  -- agonist, antagonist, inhibitor, etc.

    -- Activity (if available)
    activity_value NUMERIC,
    activity_type VARCHAR(50),
    activity_units VARCHAR(50),

    -- Source
    source VARCHAR(50),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(molecule_id, target_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS idx_silver_moltarget_mol ON mol_silver.molecule_targets(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_moltarget_target ON mol_silver.molecule_targets(target_id);

-- Publications (from OpenAlex)
CREATE TABLE IF NOT EXISTS mol_silver.publications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Identifiers
    openalex_id VARCHAR(50),
    doi VARCHAR(200),
    pmid VARCHAR(20),
    pmcid VARCHAR(20),

    -- Publication info
    title TEXT,
    abstract TEXT,
    publication_year INTEGER,
    publication_date DATE,
    journal VARCHAR(500),
    publication_type VARCHAR(50),

    -- Authors
    authors JSONB,
    first_author VARCHAR(200),

    -- Metrics
    cited_by_count INTEGER,
    is_open_access BOOLEAN,

    -- Topics
    keywords JSONB,
    concepts JSONB,
    mesh_terms JSONB,

    -- Source
    source VARCHAR(50) DEFAULT 'openalex',
    source_updated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(openalex_id)
);

CREATE INDEX IF NOT EXISTS idx_silver_pub_doi ON mol_silver.publications(doi);
CREATE INDEX IF NOT EXISTS idx_silver_pub_pmid ON mol_silver.publications(pmid);
CREATE INDEX IF NOT EXISTS idx_silver_pub_year ON mol_silver.publications(publication_year);

-- Molecule-Publication Relationships
CREATE TABLE IF NOT EXISTS mol_silver.molecule_publications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    molecule_id UUID REFERENCES mol_silver.molecules(id) ON DELETE CASCADE,
    publication_id UUID REFERENCES mol_silver.publications(id) ON DELETE CASCADE,

    -- Context
    mention_type VARCHAR(50),  -- primary_subject, mentioned, reference
    relevance_score NUMERIC(3,2),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(molecule_id, publication_id)
);

CREATE INDEX IF NOT EXISTS idx_silver_molpub_mol ON mol_silver.molecule_publications(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_molpub_pub ON mol_silver.molecule_publications(publication_id);

-- Patents
CREATE TABLE IF NOT EXISTS mol_silver.patents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    molecule_id UUID REFERENCES mol_silver.molecules(id),

    -- Patent identifiers
    patent_number VARCHAR(50) NOT NULL,
    patent_country VARCHAR(10),

    -- Dates
    filing_date DATE,
    grant_date DATE,
    expiry_date DATE,

    -- Info
    title TEXT,
    assignee VARCHAR(500),

    -- Status
    status VARCHAR(50),

    -- Source
    source VARCHAR(50),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(patent_number, patent_country)
);

CREATE INDEX IF NOT EXISTS idx_silver_patent_mol ON mol_silver.patents(molecule_id);
CREATE INDEX IF NOT EXISTS idx_silver_patent_num ON mol_silver.patents(patent_number);
CREATE INDEX IF NOT EXISTS idx_silver_patent_expiry ON mol_silver.patents(expiry_date);

-- Resolution Queue (for low-confidence records)
CREATE TABLE IF NOT EXISTS mol_silver.resolution_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    molecule_id UUID REFERENCES mol_silver.molecules(id),

    -- Resolution details
    original_identifier VARCHAR(500),
    identifier_type VARCHAR(30),
    candidate_inchi_keys JSONB,  -- Array of potential matches
    confidence_score NUMERIC(3,2),

    -- Status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, approved, rejected, merged
    resolution_action VARCHAR(20),  -- approve, reject, merge
    merge_target_id UUID REFERENCES mol_silver.molecules(id),

    -- Review
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMPTZ,
    review_notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_silver_queue_status ON mol_silver.resolution_queue(status);
CREATE INDEX IF NOT EXISTS idx_silver_queue_confidence ON mol_silver.resolution_queue(confidence_score);

-- Add comments
COMMENT ON SCHEMA silver IS 'Silver layer: Normalized, deduplicated entities with cross-source resolution';
COMMENT ON TABLE mol_silver.molecules IS 'Master molecule table with InChI Key as canonical identifier';
COMMENT ON TABLE mol_silver.identifier_mappings IS 'Cross-reference mappings between molecule IDs and source identifiers';
COMMENT ON TABLE mol_silver.resolution_queue IS 'Queue for manual review of low-confidence entity resolution';
