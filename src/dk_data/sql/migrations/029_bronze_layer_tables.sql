-- Migration 029: Bronze Layer Tables
-- Purpose: Store typed, queryable columns extracted from Raw layer
-- Part of DK Molecule Data Platform (012-dk-data-platform)

-- Create schema for bronze layer
CREATE SCHEMA IF NOT EXISTS bronze;

-- ============================================================================
-- BRONZE LAYER: Typed Columns from Source APIs
-- ============================================================================

-- ClinicalTrials.gov Bronze Table
CREATE TABLE IF NOT EXISTS bronze.clinicaltrials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Linkage to Raw layer
    raw_id UUID REFERENCES raw.clinicaltrials(id),

    -- Ingestion metadata
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'clinicaltrials_gov',
    api_version VARCHAR(20) DEFAULT 'v2',

    -- === SOURCE-NATIVE COLUMNS ===

    -- Identification Module
    nct_id VARCHAR(15) NOT NULL,
    org_study_id VARCHAR(100),
    brief_title TEXT,
    official_title TEXT,
    acronym VARCHAR(50),

    -- Status Module
    overall_status VARCHAR(50),
    last_known_status VARCHAR(50),
    start_date DATE,
    start_date_type VARCHAR(20),
    completion_date DATE,
    completion_date_type VARCHAR(20),
    study_first_submit_date DATE,
    study_first_post_date DATE,
    last_update_post_date DATE,

    -- Sponsor/Collaborators Module
    lead_sponsor_name VARCHAR(500),
    lead_sponsor_class VARCHAR(50),
    collaborators JSONB,

    -- Design Module
    study_type VARCHAR(50),
    phases JSONB,
    allocation VARCHAR(50),
    intervention_model VARCHAR(100),
    primary_purpose VARCHAR(100),
    masking VARCHAR(100),
    enrollment_count INTEGER,
    enrollment_type VARCHAR(20),

    -- Arms/Interventions Module
    arms_groups JSONB,
    interventions JSONB,

    -- Outcomes Module
    primary_outcomes JSONB,
    secondary_outcomes JSONB,

    -- Eligibility Module
    eligibility_criteria TEXT,
    sex VARCHAR(20),
    minimum_age VARCHAR(20),
    maximum_age VARCHAR(20),
    healthy_volunteers VARCHAR(10),

    -- Contacts/Locations Module
    locations JSONB,
    central_contacts JSONB,

    -- Conditions and Keywords
    conditions JSONB,
    keywords JSONB,
    mesh_terms JSONB,

    -- Processing status
    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,

    -- Record hash for change detection
    record_hash VARCHAR(64),

    UNIQUE(nct_id)
);

CREATE INDEX IF NOT EXISTS idx_bronze_ct_nct_id ON bronze.clinicaltrials(nct_id);
CREATE INDEX IF NOT EXISTS idx_bronze_ct_ingested_at ON bronze.clinicaltrials(ingested_at);
CREATE INDEX IF NOT EXISTS idx_bronze_ct_status ON bronze.clinicaltrials(overall_status);
CREATE INDEX IF NOT EXISTS idx_bronze_ct_phases ON bronze.clinicaltrials USING GIN(phases);
CREATE INDEX IF NOT EXISTS idx_bronze_ct_sponsor ON bronze.clinicaltrials(lead_sponsor_name);
CREATE INDEX IF NOT EXISTS idx_bronze_ct_processed ON bronze.clinicaltrials(processed_to_silver);

-- OpenFDA FAERS Bronze Table
CREATE TABLE IF NOT EXISTS bronze.openfda_faers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.openfda_faers(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'openfda_faers',

    -- FAERS fields
    safety_report_id VARCHAR(50) NOT NULL,
    safety_report_version INTEGER,
    receive_date DATE,
    receipt_date DATE,
    serious INTEGER,
    serious_death INTEGER,
    serious_disabling INTEGER,
    serious_hospitalization INTEGER,
    serious_life_threatening INTEGER,
    serious_other INTEGER,

    -- Patient info
    patient_age NUMERIC,
    patient_age_unit VARCHAR(20),
    patient_sex VARCHAR(10),
    patient_weight NUMERIC,

    -- Drug and reaction data (arrays)
    patient_drug JSONB,
    patient_reaction JSONB,

    -- Sender/receiver info
    sender_organization VARCHAR(200),
    receiver_organization VARCHAR(200),
    companynumb VARCHAR(50),
    occurrence_country VARCHAR(10),

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(safety_report_id, safety_report_version)
);

CREATE INDEX IF NOT EXISTS idx_bronze_faers_report ON bronze.openfda_faers(safety_report_id);
CREATE INDEX IF NOT EXISTS idx_bronze_faers_date ON bronze.openfda_faers(receive_date);
CREATE INDEX IF NOT EXISTS idx_bronze_faers_serious ON bronze.openfda_faers(serious);
CREATE INDEX IF NOT EXISTS idx_bronze_faers_processed ON bronze.openfda_faers(processed_to_silver);

-- OpenFDA Labels Bronze Table
CREATE TABLE IF NOT EXISTS bronze.openfda_labels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.openfda_labels(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'openfda_labels',

    -- Label identifiers
    set_id VARCHAR(50) NOT NULL,
    spl_id VARCHAR(50),
    version INTEGER,
    effective_time DATE,

    -- Product info
    application_number VARCHAR(20),
    brand_name TEXT,
    generic_name TEXT,
    manufacturer_name TEXT,
    product_type VARCHAR(100),
    route JSONB,
    substance_name JSONB,

    -- Label sections
    indications_and_usage TEXT,
    dosage_and_administration TEXT,
    contraindications TEXT,
    warnings TEXT,
    warnings_and_cautions TEXT,
    boxed_warning TEXT,
    adverse_reactions TEXT,
    drug_interactions TEXT,
    clinical_pharmacology TEXT,
    mechanism_of_action TEXT,
    pharmacodynamics TEXT,
    pharmacokinetics TEXT,

    -- OpenFDA enrichment
    openfda JSONB,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(set_id, version)
);

CREATE INDEX IF NOT EXISTS idx_bronze_labels_set_id ON bronze.openfda_labels(set_id);
CREATE INDEX IF NOT EXISTS idx_bronze_labels_app_num ON bronze.openfda_labels(application_number);
CREATE INDEX IF NOT EXISTS idx_bronze_labels_brand ON bronze.openfda_labels(brand_name);
CREATE INDEX IF NOT EXISTS idx_bronze_labels_generic ON bronze.openfda_labels(generic_name);
CREATE INDEX IF NOT EXISTS idx_bronze_labels_processed ON bronze.openfda_labels(processed_to_silver);

-- ChEMBL Bronze Table
CREATE TABLE IF NOT EXISTS bronze.chembl (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.chembl(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'chembl',

    -- ChEMBL identifiers
    molecule_chembl_id VARCHAR(20) NOT NULL,
    pref_name VARCHAR(500),
    molecule_type VARCHAR(50),
    max_phase INTEGER,
    first_approval INTEGER,

    -- Structure
    canonical_smiles TEXT,
    standard_inchi TEXT,
    standard_inchi_key VARCHAR(27),

    -- Properties
    molecular_formula VARCHAR(200),
    molecular_weight NUMERIC(12,4),
    alogp NUMERIC(8,4),
    hba INTEGER,
    hbd INTEGER,
    psa NUMERIC(10,4),
    rtb INTEGER,
    ro3_pass VARCHAR(10),
    num_ro5_violations INTEGER,
    aromatic_rings INTEGER,
    heavy_atoms INTEGER,
    qed_weighted NUMERIC(6,4),

    -- Classification
    atc_classifications JSONB,
    indication_class TEXT,
    drug_type VARCHAR(50),
    withdrawn_flag BOOLEAN,
    black_box_warning BOOLEAN,
    prodrug BOOLEAN,
    oral BOOLEAN,
    parenteral BOOLEAN,
    topical BOOLEAN,

    -- Targets and mechanisms
    mechanism_of_action TEXT,
    target_count INTEGER,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(molecule_chembl_id)
);

CREATE INDEX IF NOT EXISTS idx_bronze_chembl_id ON bronze.chembl(molecule_chembl_id);
CREATE INDEX IF NOT EXISTS idx_bronze_chembl_name ON bronze.chembl(pref_name);
CREATE INDEX IF NOT EXISTS idx_bronze_chembl_inchi ON bronze.chembl(standard_inchi_key);
CREATE INDEX IF NOT EXISTS idx_bronze_chembl_phase ON bronze.chembl(max_phase);
CREATE INDEX IF NOT EXISTS idx_bronze_chembl_processed ON bronze.chembl(processed_to_silver);

-- DrugBank Bronze Table
CREATE TABLE IF NOT EXISTS bronze.drugbank (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.drugbank(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'drugbank',

    -- DrugBank identifiers
    drugbank_id VARCHAR(10) NOT NULL,
    name VARCHAR(500),
    drug_type VARCHAR(50),
    cas_number VARCHAR(20),
    unii VARCHAR(15),

    -- Status
    state VARCHAR(20),
    groups JSONB,  -- approved, investigational, etc.

    -- Description
    description TEXT,
    indication TEXT,
    pharmacodynamics TEXT,
    mechanism_of_action TEXT,
    toxicity TEXT,
    metabolism TEXT,
    absorption TEXT,
    half_life VARCHAR(200),
    protein_binding VARCHAR(200),
    route_of_elimination TEXT,
    volume_of_distribution TEXT,
    clearance TEXT,

    -- Structure
    smiles TEXT,
    inchi TEXT,
    inchikey VARCHAR(27),
    molecular_formula VARCHAR(200),
    molecular_weight NUMERIC(12,4),

    -- Classifications
    atc_codes JSONB,
    categories JSONB,

    -- External links
    external_identifiers JSONB,

    -- Targets, enzymes, carriers, transporters
    targets JSONB,
    enzymes JSONB,
    carriers JSONB,
    transporters JSONB,

    -- Patents and products
    patents JSONB,
    products JSONB,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(drugbank_id)
);

CREATE INDEX IF NOT EXISTS idx_bronze_drugbank_id ON bronze.drugbank(drugbank_id);
CREATE INDEX IF NOT EXISTS idx_bronze_drugbank_name ON bronze.drugbank(name);
CREATE INDEX IF NOT EXISTS idx_bronze_drugbank_cas ON bronze.drugbank(cas_number);
CREATE INDEX IF NOT EXISTS idx_bronze_drugbank_unii ON bronze.drugbank(unii);
CREATE INDEX IF NOT EXISTS idx_bronze_drugbank_inchikey ON bronze.drugbank(inchikey);
CREATE INDEX IF NOT EXISTS idx_bronze_drugbank_processed ON bronze.drugbank(processed_to_silver);

-- PubChem Bronze Table
CREATE TABLE IF NOT EXISTS bronze.pubchem (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.pubchem(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'pubchem',

    -- PubChem identifiers
    cid BIGINT NOT NULL,
    iupac_name TEXT,
    title TEXT,

    -- Structure
    canonical_smiles TEXT,
    isomeric_smiles TEXT,
    inchi TEXT,
    inchikey VARCHAR(27),
    molecular_formula VARCHAR(200),
    molecular_weight NUMERIC(12,4),
    exact_mass NUMERIC(15,6),

    -- Properties
    xlogp NUMERIC(8,4),
    hbond_acceptor INTEGER,
    hbond_donor INTEGER,
    tpsa NUMERIC(10,4),
    rotatable_bond INTEGER,
    heavy_atom_count INTEGER,
    atom_stereo_count INTEGER,
    bond_stereo_count INTEGER,
    complexity NUMERIC(10,4),
    charge INTEGER,

    -- Synonyms
    synonyms JSONB,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(cid)
);

CREATE INDEX IF NOT EXISTS idx_bronze_pubchem_cid ON bronze.pubchem(cid);
CREATE INDEX IF NOT EXISTS idx_bronze_pubchem_inchikey ON bronze.pubchem(inchikey);
CREATE INDEX IF NOT EXISTS idx_bronze_pubchem_processed ON bronze.pubchem(processed_to_silver);

-- UniProt Bronze Table
CREATE TABLE IF NOT EXISTS bronze.uniprot (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.uniprot(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'uniprot',

    -- UniProt identifiers
    accession VARCHAR(15) NOT NULL,
    entry_name VARCHAR(50),
    protein_name TEXT,

    -- Gene info
    gene_names JSONB,
    organism VARCHAR(200),
    organism_id INTEGER,

    -- Sequence
    sequence TEXT,
    sequence_length INTEGER,
    sequence_mass INTEGER,

    -- Function
    function_description TEXT,
    subcellular_location JSONB,
    tissue_specificity TEXT,

    -- Features
    features JSONB,

    -- Cross-references
    pdb_ids JSONB,
    drugbank_ids JSONB,
    chembl_ids JSONB,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(accession)
);

CREATE INDEX IF NOT EXISTS idx_bronze_uniprot_acc ON bronze.uniprot(accession);
CREATE INDEX IF NOT EXISTS idx_bronze_uniprot_entry ON bronze.uniprot(entry_name);
CREATE INDEX IF NOT EXISTS idx_bronze_uniprot_processed ON bronze.uniprot(processed_to_silver);

-- PDB Bronze Table
CREATE TABLE IF NOT EXISTS bronze.pdb (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.pdb(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'pdb',

    -- PDB identifiers
    pdb_id VARCHAR(10) NOT NULL,
    title TEXT,
    method VARCHAR(50),
    resolution NUMERIC(5,2),

    -- Structure info
    release_date DATE,
    deposit_date DATE,
    revision_date DATE,
    polymer_entity_count INTEGER,
    nonpolymer_entity_count INTEGER,

    -- Organism
    source_organism VARCHAR(200),
    source_organism_id INTEGER,

    -- Entities
    entities JSONB,
    ligands JSONB,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(pdb_id)
);

CREATE INDEX IF NOT EXISTS idx_bronze_pdb_id ON bronze.pdb(pdb_id);
CREATE INDEX IF NOT EXISTS idx_bronze_pdb_processed ON bronze.pdb(processed_to_silver);

-- SIDER Bronze Table
CREATE TABLE IF NOT EXISTS bronze.sider (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.sider(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'sider',

    -- SIDER identifiers (STITCH uses CID format)
    stitch_id VARCHAR(20) NOT NULL,
    drug_name VARCHAR(500),

    -- Side effect info
    meddra_concept_type VARCHAR(20),
    meddra_umls_id VARCHAR(20),
    meddra_concept_name TEXT,
    side_effect_name TEXT,

    -- Frequency
    frequency VARCHAR(100),
    frequency_lower NUMERIC(8,6),
    frequency_upper NUMERIC(8,6),

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_bronze_sider_stitch ON bronze.sider(stitch_id);
CREATE INDEX IF NOT EXISTS idx_bronze_sider_drug ON bronze.sider(drug_name);
CREATE INDEX IF NOT EXISTS idx_bronze_sider_processed ON bronze.sider(processed_to_silver);

-- OpenAlex Bronze Table
CREATE TABLE IF NOT EXISTS bronze.openalex (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES raw.openalex(id),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id VARCHAR(50) NOT NULL DEFAULT 'openalex',

    -- OpenAlex identifiers
    work_id VARCHAR(50) NOT NULL,
    doi VARCHAR(200),
    pmid VARCHAR(20),
    pmcid VARCHAR(20),

    -- Publication info
    title TEXT,
    publication_year INTEGER,
    publication_date DATE,
    type VARCHAR(50),
    language VARCHAR(10),

    -- Source
    source_display_name VARCHAR(500),
    source_type VARCHAR(50),
    is_oa BOOLEAN,
    oa_status VARCHAR(50),
    oa_url TEXT,

    -- Metrics
    cited_by_count INTEGER,
    cited_by_percentile_year JSONB,
    counts_by_year JSONB,

    -- Content
    abstract TEXT,
    keywords JSONB,
    concepts JSONB,
    topics JSONB,
    mesh JSONB,

    -- Authors
    authorships JSONB,

    processed_to_silver BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,
    record_hash VARCHAR(64),

    UNIQUE(work_id)
);

CREATE INDEX IF NOT EXISTS idx_bronze_openalex_id ON bronze.openalex(work_id);
CREATE INDEX IF NOT EXISTS idx_bronze_openalex_doi ON bronze.openalex(doi);
CREATE INDEX IF NOT EXISTS idx_bronze_openalex_pmid ON bronze.openalex(pmid);
CREATE INDEX IF NOT EXISTS idx_bronze_openalex_year ON bronze.openalex(publication_year);
CREATE INDEX IF NOT EXISTS idx_bronze_openalex_processed ON bronze.openalex(processed_to_silver);

-- Add comments
COMMENT ON SCHEMA bronze IS 'Bronze layer: Typed columns extracted from Raw API responses';
