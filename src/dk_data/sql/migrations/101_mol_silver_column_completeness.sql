-- Migration 101: Column completeness audit — promote all bronze columns to silver
-- Feature: 019-cms-puf-platform-reconciliation
-- Reason: Zero column loss policy audit found columns dropped without justification
--   across 5 existing silver models and 4 bronze sources with no silver model at all.
--
-- Changes per table:
--   mol_silver.molecules          — physicochemical props (ChEMBL + PubChem) + DrugBank enrichment
--   mol_silver.clinical_trials    — eligibility, dates, results, oversight columns
--   mol_silver.drug_labels        — population guidance, pharmacodynamics, storage sections
--   mol_silver.adverse_events     — FAERS seriousness sub-type counts
--   mol_silver.publications       — Cochrane conclusions/interventions/conditions
--   mol_silver.drug_pharmacology  — NEW TABLE (DrugBank pharmacology)
--   mol_silver.proteins           — NEW TABLE (UniProt protein records)
--   mol_silver.research_grants    — NEW TABLE (NIH Reporter grants; schema corrected)
--   mol_silver.protein_structures — NEW TABLE (PDB structures)
--   mol_silver.company_financials — NEW TABLE (SEC EDGAR filings)

BEGIN;

-- ============================================================================
-- mol_silver.molecules — physicochemical properties + DrugBank enrichment
-- ============================================================================

-- ChEMBL physicochemical (documented as "restored" in COLUMN_LINEAGE but missing from SQL)
ALTER TABLE mol_silver.molecules
    ADD COLUMN IF NOT EXISTS alogp                NUMERIC,
    ADD COLUMN IF NOT EXISTS hba                  INTEGER,
    ADD COLUMN IF NOT EXISTS hbd                  INTEGER,
    ADD COLUMN IF NOT EXISTS psa                  NUMERIC,
    ADD COLUMN IF NOT EXISTS num_ro5_violations   INTEGER,
    ADD COLUMN IF NOT EXISTS aromatic_rings       INTEGER,
    ADD COLUMN IF NOT EXISTS heavy_atoms          INTEGER;

-- PubChem-specific physicochemical (no ChEMBL equivalent)
ALTER TABLE mol_silver.molecules
    ADD COLUMN IF NOT EXISTS exact_mass           NUMERIC,
    ADD COLUMN IF NOT EXISTS isomeric_smiles      TEXT,
    ADD COLUMN IF NOT EXISTS rotatable_bond_count INTEGER,
    ADD COLUMN IF NOT EXISTS complexity           NUMERIC,
    ADD COLUMN IF NOT EXISTS charge               INTEGER,
    ADD COLUMN IF NOT EXISTS mesh_headings        JSONB,
    ADD COLUMN IF NOT EXISTS pharmacological_actions JSONB;

-- DrugBank pharmacology enrichment (populated via LEFT JOIN in molecules.sql)
ALTER TABLE mol_silver.molecules
    ADD COLUMN IF NOT EXISTS description          TEXT,
    ADD COLUMN IF NOT EXISTS pharmacodynamics     TEXT,
    ADD COLUMN IF NOT EXISTS drug_categories      JSONB;

COMMENT ON COLUMN mol_silver.molecules.alogp IS 'Lipophilicity (ChEMBL ALogP; PubChem XLogP mapped to same column). NULL for DrugBank-only molecules.';
COMMENT ON COLUMN mol_silver.molecules.hba IS 'H-bond acceptor count. NULL for DrugBank-only molecules.';
COMMENT ON COLUMN mol_silver.molecules.hbd IS 'H-bond donor count. NULL for DrugBank-only molecules.';
COMMENT ON COLUMN mol_silver.molecules.psa IS 'Polar surface area Å² (ChEMBL PSA; PubChem TPSA mapped to same column). NULL for DrugBank-only molecules.';
COMMENT ON COLUMN mol_silver.molecules.num_ro5_violations IS 'Lipinski Rule-of-5 violations (ChEMBL only). NULL for PubChem and DrugBank molecules.';
COMMENT ON COLUMN mol_silver.molecules.aromatic_rings IS 'Aromatic ring count (ChEMBL only). NULL for PubChem and DrugBank molecules.';
COMMENT ON COLUMN mol_silver.molecules.heavy_atoms IS 'Non-hydrogen atom count (ChEMBL heavy_atoms; PubChem heavy_atom_count mapped to same column).';
COMMENT ON COLUMN mol_silver.molecules.exact_mass IS 'Exact monoisotopic mass (PubChem only). NULL for ChEMBL and DrugBank molecules.';
COMMENT ON COLUMN mol_silver.molecules.isomeric_smiles IS 'Isomeric SMILES including stereo (PubChem only). NULL for ChEMBL and DrugBank molecules.';
COMMENT ON COLUMN mol_silver.molecules.rotatable_bond_count IS 'Rotatable bond count (PubChem only). NULL for ChEMBL and DrugBank molecules.';
COMMENT ON COLUMN mol_silver.molecules.complexity IS 'Molecular complexity score (PubChem only). NULL for ChEMBL and DrugBank molecules.';
COMMENT ON COLUMN mol_silver.molecules.charge IS 'Formal molecular charge (PubChem only). NULL for ChEMBL and DrugBank molecules.';
COMMENT ON COLUMN mol_silver.molecules.mesh_headings IS 'MeSH headings JSONB array (PubChem only). NULL for ChEMBL and DrugBank molecules.';
COMMENT ON COLUMN mol_silver.molecules.pharmacological_actions IS 'Pharmacological action classes JSONB array (PubChem only).';
COMMENT ON COLUMN mol_silver.molecules.description IS 'DrugBank drug description text. NULL for ChEMBL/PubChem-only molecules.';
COMMENT ON COLUMN mol_silver.molecules.pharmacodynamics IS 'DrugBank pharmacodynamics text. NULL for ChEMBL/PubChem-only molecules.';
COMMENT ON COLUMN mol_silver.molecules.drug_categories IS 'DrugBank category classification JSONB array. NULL for ChEMBL/PubChem-only molecules.';

-- ============================================================================
-- mol_silver.clinical_trials — eligibility, dates, results, oversight
-- ============================================================================

ALTER TABLE mol_silver.clinical_trials
    -- Previously dropped without justification — all exist in bronze
    ADD COLUMN IF NOT EXISTS acronym              TEXT,
    ADD COLUMN IF NOT EXISTS last_known_status    TEXT,
    ADD COLUMN IF NOT EXISTS why_stopped          TEXT,
    ADD COLUMN IF NOT EXISTS phases_raw           JSONB,
    ADD COLUMN IF NOT EXISTS first_submit_date    DATE,
    ADD COLUMN IF NOT EXISTS first_post_date      DATE,
    ADD COLUMN IF NOT EXISTS last_update_date     DATE,
    ADD COLUMN IF NOT EXISTS keywords             JSONB,
    ADD COLUMN IF NOT EXISTS arm_groups           JSONB,
    ADD COLUMN IF NOT EXISTS enrollment_type      TEXT,
    ADD COLUMN IF NOT EXISTS eligibility_sex      TEXT,
    ADD COLUMN IF NOT EXISTS minimum_age          TEXT,
    ADD COLUMN IF NOT EXISTS maximum_age          TEXT,
    ADD COLUMN IF NOT EXISTS healthy_volunteers   TEXT,
    ADD COLUMN IF NOT EXISTS eligibility_criteria TEXT,
    ADD COLUMN IF NOT EXISTS lead_sponsor_class   TEXT,
    ADD COLUMN IF NOT EXISTS responsible_party    JSONB,
    ADD COLUMN IF NOT EXISTS central_contacts     JSONB,
    ADD COLUMN IF NOT EXISTS locations            JSONB,
    ADD COLUMN IF NOT EXISTS results_section      JSONB,
    -- Extracted from raw_json.protocolSection.oversightModule
    ADD COLUMN IF NOT EXISTS fda_regulated_drug   BOOLEAN,
    ADD COLUMN IF NOT EXISTS fda_regulated_device BOOLEAN,
    ADD COLUMN IF NOT EXISTS has_dmc              BOOLEAN;

-- Fix time_column: silver was referencing ingested_at which doesn't exist in bronze;
-- source_updated_at (= request_timestamp) is the correct column.
-- No DDL needed — this is a SQLMesh model definition change only.

-- ============================================================================
-- mol_silver.drug_labels — population guidance + pharmacodynamics sections
-- ============================================================================

ALTER TABLE mol_silver.drug_labels
    ADD COLUMN IF NOT EXISTS use_in_specific_populations TEXT,
    ADD COLUMN IF NOT EXISTS pharmacodynamics             TEXT,
    ADD COLUMN IF NOT EXISTS nursing_mothers              TEXT,
    ADD COLUMN IF NOT EXISTS storage_and_handling         TEXT,
    ADD COLUMN IF NOT EXISTS principal_display_panel      TEXT,
    ADD COLUMN IF NOT EXISTS is_original_packager         BOOLEAN,
    ADD COLUMN IF NOT EXISTS spl_set_ids                  JSONB,
    ADD COLUMN IF NOT EXISTS nui                          JSONB;

COMMENT ON COLUMN mol_silver.drug_labels.use_in_specific_populations IS 'FDA label section: use in specific populations (pregnancy, nursing, pediatric, geriatric combined). Previously dropped without justification.';
COMMENT ON COLUMN mol_silver.drug_labels.pharmacodynamics IS 'FDA label pharmacodynamics section. Previously dropped without justification.';
COMMENT ON COLUMN mol_silver.drug_labels.nursing_mothers IS 'FDA label nursing mothers section. Previously dropped without justification.';
COMMENT ON COLUMN mol_silver.drug_labels.storage_and_handling IS 'FDA label storage and handling section.';
COMMENT ON COLUMN mol_silver.drug_labels.principal_display_panel IS 'FDA label principal display panel text (label front-page text).';

-- ============================================================================
-- mol_silver.adverse_events — FAERS seriousness sub-type counts
-- ============================================================================

ALTER TABLE mol_silver.adverse_events
    ADD COLUMN IF NOT EXISTS lifethreatening_count INTEGER,
    ADD COLUMN IF NOT EXISTS disabling_count        INTEGER,
    ADD COLUMN IF NOT EXISTS congenital_count       INTEGER,
    ADD COLUMN IF NOT EXISTS other_serious_count    INTEGER;

COMMENT ON COLUMN mol_silver.adverse_events.lifethreatening_count IS 'Count of FAERS reports with seriousnesslifethreatening=1 for this drug-event pair.';
COMMENT ON COLUMN mol_silver.adverse_events.disabling_count IS 'Count of FAERS reports with seriousnessdisabling=1 for this drug-event pair.';
COMMENT ON COLUMN mol_silver.adverse_events.congenital_count IS 'Count of FAERS reports with seriousnesscongenitalanomali=1 for this drug-event pair.';
COMMENT ON COLUMN mol_silver.adverse_events.other_serious_count IS 'Count of FAERS reports with seriousnessother=1 for this drug-event pair.';

-- ============================================================================
-- mol_silver.publications — Cochrane conclusions/interventions/conditions
-- ============================================================================

ALTER TABLE mol_silver.publications
    ADD COLUMN IF NOT EXISTS conclusions           TEXT,
    ADD COLUMN IF NOT EXISTS interventions_reviewed JSONB,
    ADD COLUMN IF NOT EXISTS conditions_reviewed   JSONB;

COMMENT ON COLUMN mol_silver.publications.conclusions IS 'Cochrane review conclusions text. NULL for non-Cochrane publications.';
COMMENT ON COLUMN mol_silver.publications.interventions_reviewed IS 'Cochrane review interventions JSONB array (from TEXT[] bronze column). NULL for non-Cochrane publications.';
COMMENT ON COLUMN mol_silver.publications.conditions_reviewed IS 'Cochrane review conditions JSONB array (from TEXT[] bronze column). NULL for non-Cochrane publications.';

-- ============================================================================
-- mol_silver.drug_pharmacology — NEW TABLE (DrugBank pharmacology)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_silver.drug_pharmacology (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id             UUID        REFERENCES mol_silver.molecules(molecule_id),
    drugbank_id             TEXT        NOT NULL UNIQUE,
    cas_number              TEXT,
    name                    TEXT,
    description             TEXT,
    indication              TEXT,
    pharmacodynamics        TEXT,
    mechanism_of_action     TEXT,
    absorption              TEXT,
    protein_binding         TEXT,
    metabolism              TEXT,
    half_life               TEXT,
    route_of_elimination    TEXT,
    clearance               TEXT,
    volume_of_distribution  TEXT,
    toxicity                TEXT,
    categories              JSONB,
    targets                 JSONB,
    enzymes                 JSONB,
    carriers                JSONB,
    transporters            JSONB,
    pathways                JSONB,
    drug_interactions       JSONB,
    food_interactions       JSONB,
    classification          JSONB,
    atc_codes               JSONB,
    groups                  JSONB,
    unii                    TEXT,
    external_links          JSONB,
    external_identifiers    JSONB,
    fda_label               JSONB,
    patents                 JSONB,
    calculated_properties   JSONB,
    smiles                  TEXT,
    inchi                   TEXT,
    inchi_key               TEXT,
    molecular_formula       TEXT,
    average_mass            NUMERIC,
    monoisotopic_mass       NUMERIC,
    drug_type               TEXT,
    state                   TEXT,
    synonyms                JSONB,
    international_brands    JSONB,
    products                JSONB,
    source                  TEXT,
    source_updated_at       TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- mol_silver.proteins — NEW TABLE (UniProt protein records)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_silver.proteins (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id         UUID        REFERENCES mol_silver.molecules(molecule_id),
    uniprot_id          TEXT        NOT NULL UNIQUE,
    entry_name          TEXT,
    entry_type          TEXT,
    protein_name        TEXT,
    short_name          TEXT,
    alternative_names   JSONB,
    submission_names    JSONB,
    gene_name           TEXT,
    genes               JSONB,
    organism_scientific TEXT,
    organism_common     TEXT,
    taxonomy_id         INTEGER,
    lineage             JSONB,
    sequence            TEXT,
    sequence_length     INTEGER,
    molecular_weight    INTEGER,
    sequence_checksum   TEXT,
    comments            JSONB,
    features            JSONB,
    keywords            JSONB,
    go_terms            JSONB,
    annotation_score    NUMERIC,
    cross_references    JSONB,
    secondary_accessions JSONB,
    pdb_structures      JSONB,
    extra_attributes    JSONB,
    source              TEXT,
    source_updated_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- mol_silver.research_grants — schema corrected to match actual bronze columns
-- (Previous version referenced pi_name, pi_institution, funding_agency which
--  do not exist in mol_bronze.nih_reporter)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_silver.research_grants (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id         UUID        REFERENCES mol_silver.molecules(molecule_id),
    appl_id             INTEGER,
    project_num         TEXT        NOT NULL UNIQUE,
    study_section       TEXT,
    project_title       TEXT        NOT NULL,
    fiscal_year         INTEGER,
    activity_code       TEXT,
    mechanism_code      TEXT,
    funding_mechanism   TEXT,
    pi_names            JSONB,
    program_officials   JSONB,
    organization_name   TEXT,
    organization_city   TEXT,
    organization_state  TEXT,
    organization_country TEXT,
    award_amount        NUMERIC,
    total_cost          NUMERIC,
    abstract_text       TEXT,
    terms               TEXT,
    project_start_date  DATE,
    project_end_date    DATE,
    source              TEXT,
    source_updated_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- mol_silver.protein_structures — NEW TABLE (PDB structures)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_silver.protein_structures (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id         UUID        REFERENCES mol_silver.molecules(molecule_id),
    pdb_id              TEXT        NOT NULL UNIQUE,
    title               TEXT,
    method              TEXT,
    resolution          NUMERIC,
    molecular_weight    NUMERIC,
    deposit_date        DATE,
    release_date        DATE,
    polymer_entities    JSONB,
    nonpolymer_entities JSONB,
    ligand_id           TEXT,
    ligand_name         TEXT,
    uniprot_id          TEXT,
    source_organism     TEXT,
    taxonomy_id         INTEGER,
    source              TEXT,
    source_updated_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- mol_silver.company_financials — NEW TABLE (SEC EDGAR filings)
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_silver.company_financials (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    filing_id       TEXT        NOT NULL UNIQUE,
    cik             TEXT        NOT NULL,
    company_name    TEXT,
    filing_type     TEXT,
    filing_date     DATE,
    document_url    TEXT,
    description     TEXT,
    revenue         NUMERIC,
    net_income      NUMERIC,
    total_assets    NUMERIC,
    source          TEXT,
    source_updated_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMIT;
