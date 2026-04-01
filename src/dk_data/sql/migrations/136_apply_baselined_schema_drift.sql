-- Migration 136: Apply all schema drift from baselined migrations 100–125
-- Feature: 024-drugbank-loader-transaction-fix
--
-- Root cause: migrations 020–126 were recorded as 'baselined' (SQL never executed)
-- because the database was initialised from init_database.sql and then stamped.
-- init_database.sql was not kept in sync, so migrations 100–125 added tables and
-- columns that never landed in the cluster.
--
-- This migration is fully idempotent (CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
-- DROP TABLE IF EXISTS before full recreates of staging tables with wrong schemas).
--
-- Sources covered (in dependency order):
--   100  mol_silver.molecules ChEMBL flags
--   101  mol_silver column completeness + 5 new silver tables
--   103  meta platform tables (pipeline_jobs, transformation_config, etc.)
--   105  hcs_raw.hrsa_shortage_areas
--   107  mol_raw.uspto_patents patent_type/kind
--   108  mol_raw.epo_patents cpc_codes
--   109  hcs_raw.hrsa_shortage_areas hpsa_status
--   112  mol_raw.openalex_ci 21 extended columns
--   113  raw.cms_geographic_variation (superseded by hcs_raw version in 117)
--   115  mol_raw.europepmc_raw
--   117  hcs_silver agent schema fixes + CMS PUF table corrections + agent schema move
--   121  mol_raw tables for 7 new molecule sources

-- Transaction managed by the migration runner (psycopg2 autobegin).
-- Do NOT add BEGIN;/COMMIT; here — runner wraps each migration in its own transaction.

-- ============================================================================
-- PREREQUISITE: ensure HCS schemas exist (migration 086 may have been baselined)
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS hcs_raw;
CREATE SCHEMA IF NOT EXISTS hcs_bronze;
CREATE SCHEMA IF NOT EXISTS hcs_silver;
CREATE SCHEMA IF NOT EXISTS hcs_gold;

-- ============================================================================
-- PREREQUISITE: mol_silver tables from migration 040 (baselined — not in init_database.sql)
-- Only created if the named relation does not already exist (table or view).
-- FK constraints are omitted here because parent tables may only be VIEWs in
-- SQLMesh-managed environments; FK enforcement is delegated to the application.
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema='mol_silver' AND table_name='publications') THEN
        CREATE TABLE mol_silver.publications (
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            openalex_id         VARCHAR(50),
            doi                 VARCHAR(200),
            pmid                VARCHAR(20),
            pmcid               VARCHAR(20),
            title               TEXT,
            abstract            TEXT,
            publication_year    INTEGER,
            publication_date    DATE,
            journal             VARCHAR(500),
            publication_type    VARCHAR(50),
            authors             JSONB,
            first_author        VARCHAR(200),
            cited_by_count      INTEGER,
            is_open_access      BOOLEAN,
            keywords            JSONB,
            concepts            JSONB,
            mesh_terms          JSONB,
            source              VARCHAR(50) DEFAULT 'openalex',
            source_updated_at   TIMESTAMPTZ,
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(openalex_id)
        );
        CREATE INDEX idx_silver_pub_doi  ON mol_silver.publications(doi);
        CREATE INDEX idx_silver_pub_pmid ON mol_silver.publications(pmid);
        CREATE INDEX idx_silver_pub_year ON mol_silver.publications(publication_year);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema='mol_silver' AND table_name='molecule_targets') THEN
        CREATE TABLE mol_silver.molecule_targets (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            molecule_id       UUID,
            target_id         UUID,
            relationship_type VARCHAR(50),
            action_type       VARCHAR(50),
            activity_value    NUMERIC,
            activity_type     VARCHAR(50),
            activity_units    VARCHAR(50),
            source            VARCHAR(50),
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(molecule_id, target_id, relationship_type)
        );
        CREATE INDEX idx_silver_moltarget_mol    ON mol_silver.molecule_targets(molecule_id);
        CREATE INDEX idx_silver_moltarget_target ON mol_silver.molecule_targets(target_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema='mol_silver' AND table_name='molecule_publications') THEN
        CREATE TABLE mol_silver.molecule_publications (
            id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            molecule_id    UUID,
            publication_id UUID,
            mention_type   VARCHAR(50),
            relevance_score NUMERIC(3,2),
            created_at     TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(molecule_id, publication_id)
        );
        CREATE INDEX idx_silver_molpub_mol ON mol_silver.molecule_publications(molecule_id);
        CREATE INDEX idx_silver_molpub_pub ON mol_silver.molecule_publications(publication_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema='mol_silver' AND table_name='patents') THEN
        CREATE TABLE mol_silver.patents (
            id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            molecule_id    UUID,
            patent_number  VARCHAR(50) NOT NULL,
            patent_country VARCHAR(10),
            filing_date    DATE,
            grant_date     DATE,
            expiry_date    DATE,
            title          TEXT,
            assignee       VARCHAR(500),
            status         VARCHAR(50),
            source         VARCHAR(50),
            created_at     TIMESTAMPTZ DEFAULT NOW(),
            updated_at     TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(patent_number, patent_country)
        );
        CREATE INDEX idx_silver_patent_mol    ON mol_silver.patents(molecule_id);
        CREATE INDEX idx_silver_patent_num    ON mol_silver.patents(patent_number);
        CREATE INDEX idx_silver_patent_expiry ON mol_silver.patents(expiry_date);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema='mol_silver' AND table_name='resolution_queue') THEN
        CREATE TABLE mol_silver.resolution_queue (
            id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            molecule_id           UUID,
            original_identifier   VARCHAR(500),
            identifier_type       VARCHAR(30),
            candidate_inchi_keys  JSONB,
            confidence_score      NUMERIC(3,2),
            status                VARCHAR(20) DEFAULT 'pending',
            resolution_action     VARCHAR(20),
            merge_target_id       UUID,
            reviewed_by           VARCHAR(100),
            reviewed_at           TIMESTAMPTZ,
            review_notes          TEXT,
            created_at            TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX idx_silver_queue_status     ON mol_silver.resolution_queue(status);
        CREATE INDEX idx_silver_queue_confidence ON mol_silver.resolution_queue(confidence_score);
    END IF;
END $$;

-- ============================================================================
-- PREREQUISITE: hcs_raw CMS tables from migration 085 (may be baselined on cluster)
-- These tables are ALTER TABLE'd below — must exist first.
-- Tables that are DROP+CREATE'd later in this migration don't need CREATE IF NOT EXISTS here.
-- ============================================================================
CREATE TABLE IF NOT EXISTS hcs_raw.cms_nppes (
    id                                                      BIGSERIAL PRIMARY KEY,
    npi                                                     TEXT NOT NULL,
    entity_type_code                                        TEXT,
    provider_last_name                                      TEXT,
    provider_first_name                                     TEXT,
    provider_organization_name                              TEXT,
    provider_credential_text                                TEXT,
    provider_first_line_business_mailing_address            TEXT,
    provider_second_line_business_mailing_address           TEXT,
    provider_business_mailing_address_city_name             TEXT,
    provider_business_mailing_address_state_name            TEXT,
    provider_business_mailing_address_postal_code           TEXT,
    provider_business_mailing_address_telephone_number      TEXT,
    provider_first_line_business_practice_location_address  TEXT,
    provider_second_line_business_practice_location_address TEXT,
    provider_business_practice_location_address_city_name   TEXT,
    provider_business_practice_location_address_state_name  TEXT,
    provider_business_practice_location_address_postal_code TEXT,
    provider_business_practice_location_address_country_code TEXT,
    provider_business_practice_location_address_telephone_number TEXT,
    provider_business_practice_location_address_fax_number  TEXT,
    healthcare_provider_taxonomy_code_1                     TEXT,
    healthcare_provider_taxonomy_code_2                     TEXT,
    npi_deactivation_date                                   DATE,
    npi_reactivation_date                                   DATE,
    _source_year                                            INTEGER NOT NULL,
    _source_hash                                            TEXT NOT NULL,
    _source_file                                            TEXT,
    _loaded_at                                              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, _source_year)
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_open_payments (
    id                                                      BIGSERIAL PRIMARY KEY,
    covered_recipient_type                                  TEXT,
    physician_profile_id                                    TEXT,
    physician_first_name                                    TEXT,
    physician_last_name                                     TEXT,
    physician_specialty                                     TEXT,
    applicable_manufacturer_or_gpo_name                     TEXT,
    total_amount_of_payment_usdollars                       NUMERIC(18,2),
    date_of_payment                                         DATE,
    number_of_payments_included_in_total_amount             INTEGER,
    form_of_payment_or_transfer_of_value                    TEXT,
    nature_of_payment_or_transfer_of_value                  TEXT,
    recipient_city                                          TEXT,
    recipient_state                                         TEXT,
    recipient_zip_code                                      TEXT,
    payment_publication_date                                DATE,
    record_id                                               TEXT,
    program_year                                            INTEGER,
    name_of_drug_or_biological_or_device_or_medical_supply_1 TEXT,
    name_of_drug_or_biological_or_device_or_medical_supply_2 TEXT,
    name_of_drug_or_biological_or_device_or_medical_supply_3 TEXT,
    name_of_drug_or_biological_or_device_or_medical_supply_4 TEXT,
    name_of_drug_or_biological_or_device_or_medical_supply_5 TEXT,
    associated_drug_or_biological_ndc_1                     TEXT,
    associated_drug_or_biological_ndc_2                     TEXT,
    associated_drug_or_biological_ndc_3                     TEXT,
    associated_drug_or_biological_ndc_4                     TEXT,
    associated_drug_or_biological_ndc_5                     TEXT,
    drug_name_1_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_1,''), '[^a-z0-9 ]', '', 'g'))) STORED,
    drug_name_2_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_2,''), '[^a-z0-9 ]', '', 'g'))) STORED,
    drug_name_3_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_3,''), '[^a-z0-9 ]', '', 'g'))) STORED,
    drug_name_4_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_4,''), '[^a-z0-9 ]', '', 'g'))) STORED,
    drug_name_5_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_5,''), '[^a-z0-9 ]', '', 'g'))) STORED,
    _source_year                                            INTEGER NOT NULL,
    _source_hash                                            TEXT NOT NULL,
    _source_file                                            TEXT,
    _loaded_at                                              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_inpatient_puf (
    id                          BIGSERIAL PRIMARY KEY,
    drg_cd                      TEXT,
    drg_definition              TEXT,
    provider_id                 TEXT,
    provider_name               TEXT,
    provider_street_address     TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_state_fips         TEXT,
    provider_zip_code           TEXT,
    provider_ruca               TEXT,
    hospital_referral_region_desc TEXT,
    total_discharges            INTEGER,
    average_covered_charges     NUMERIC(18,2),
    average_total_payments      NUMERIC(18,2),
    average_medicare_payments   NUMERIC(18,2),
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (_source_hash, provider_id, drg_definition, _source_year)
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf (
    id                               BIGSERIAL PRIMARY KEY,
    npi                              TEXT,
    nppes_provider_last_org_name     TEXT,
    nppes_provider_first_name        TEXT,
    nppes_provider_mi                TEXT,
    nppes_credentials                TEXT,
    nppes_provider_gender            TEXT,
    nppes_entity_code                TEXT,
    nppes_provider_street1           TEXT,
    nppes_provider_street2           TEXT,
    nppes_provider_city              TEXT,
    nppes_provider_state             TEXT,
    nppes_provider_state_fips        TEXT,
    nppes_provider_zip               TEXT,
    nppes_provider_ruca              TEXT,
    nppes_provider_country           TEXT,
    provider_type                    TEXT,
    medicare_participation_indicator TEXT,
    number_of_hcpcs                  INTEGER,
    total_services                   NUMERIC(18,2),
    total_unique_benes               INTEGER,
    total_submitted_chrg_amt         NUMERIC(18,2),
    total_medicare_allowed_amt       NUMERIC(18,2),
    total_medicare_payment_amt       NUMERIC(18,2),
    total_medicare_stnd_amt          NUMERIC(18,2),
    _source_year                     INTEGER NOT NULL,
    _source_hash                     TEXT NOT NULL,
    _source_file                     TEXT,
    _loaded_at                       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, _source_year)
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospital_general_info (
    id                          BIGSERIAL PRIMARY KEY,
    facility_id                 TEXT,
    facility_name               TEXT,
    address                     TEXT,
    city_town                   TEXT,
    state                       TEXT,
    zip_code                    TEXT,
    county_parish               TEXT,
    telephone_number            TEXT,
    hospital_type               TEXT,
    hospital_ownership          TEXT,
    emergency_services          TEXT,
    meets_criteria_for_birthing_friendly_designation TEXT,
    hospital_overall_rating     INTEGER,
    hospital_overall_rating_footnote TEXT,
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (facility_id, _source_year)
);

-- ============================================================================
-- PREREQUISITE: hcs_silver agent output tables from migration 085 (may be baselined)
-- ============================================================================
CREATE TABLE IF NOT EXISTS hcs_silver.service_lines (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    npi              TEXT        NOT NULL,
    service_line     TEXT        NOT NULL,
    confidence_score NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review     BOOLEAN     NOT NULL DEFAULT FALSE,
    agent_output     JSONB,
    _source_year     INTEGER,
    _loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, service_line, _source_year)
);
CREATE TABLE IF NOT EXISTS hcs_silver.idn_hierarchy (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    child_npi           TEXT        NOT NULL,
    parent_organization TEXT        NOT NULL,
    relationship_type   TEXT,
    confidence_score    NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review        BOOLEAN     NOT NULL DEFAULT FALSE,
    agent_output        JSONB,
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (child_npi, parent_organization)
);
CREATE TABLE IF NOT EXISTS hcs_silver.referral_network (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    referring_npi    TEXT        NOT NULL,
    receiving_npi    TEXT        NOT NULL,
    referral_volume  INTEGER,
    confidence_score NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review     BOOLEAN     NOT NULL DEFAULT FALSE,
    agent_output     JSONB,
    _source_year     INTEGER,
    _loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (referring_npi, receiving_npi, _source_year)
);
CREATE TABLE IF NOT EXISTS hcs_silver.verified_contacts (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    npi                 TEXT        NOT NULL,
    verified_phone      TEXT,
    verified_email      TEXT,
    verification_status TEXT        NOT NULL,
    confidence_score    NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review        BOOLEAN     NOT NULL DEFAULT FALSE,
    agent_output        JSONB,
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi)
);
CREATE TABLE IF NOT EXISTS hcs_silver.staffing_decomposition (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id      TEXT        NOT NULL,
    role_category    TEXT        NOT NULL,
    fte_estimate     NUMERIC(10,2),
    confidence_score NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review     BOOLEAN     NOT NULL DEFAULT FALSE,
    agent_output     JSONB,
    _source_year     INTEGER,
    _loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, role_category, _source_year)
);
CREATE TABLE IF NOT EXISTS hcs_silver.equipment_inventory (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    npi                TEXT        NOT NULL,
    equipment_category TEXT        NOT NULL,
    hcpcs_evidence     JSONB,
    confidence_score   NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review       BOOLEAN     NOT NULL DEFAULT FALSE,
    agent_output       JSONB,
    _source_year       INTEGER,
    _loaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, equipment_category, _source_year)
);

-- mol_raw.nih_reporter_raw (from migration 085, may be baselined on cluster)
CREATE TABLE IF NOT EXISTS mol_raw.nih_reporter_raw (
    id                  BIGSERIAL   PRIMARY KEY,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_status     INTEGER     NOT NULL DEFAULT 200,
    response_body       JSONB       NOT NULL,
    processed_to_bronze BOOLEAN     NOT NULL DEFAULT FALSE,
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_nih_reporter_raw_project_num
    ON mol_raw.nih_reporter_raw ((response_body->>'project_num'))
    WHERE response_body->>'project_num' IS NOT NULL;

-- ============================================================================
-- FROM 100: mol_silver.molecules — ChEMBL flags
-- Skipped if molecules is a VIEW (SQLMesh-managed environment).
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='mol_silver' AND table_name='molecules' AND table_type='BASE TABLE') THEN
        ALTER TABLE mol_silver.molecules
            ADD COLUMN IF NOT EXISTS prodrug         BOOLEAN,
            ADD COLUMN IF NOT EXISTS natural_product BOOLEAN,
            ADD COLUMN IF NOT EXISTS usan_stem       TEXT;
    END IF;
END $$;

-- ============================================================================
-- FROM 101: mol_silver.molecules — physicochemical + DrugBank enrichment
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='mol_silver' AND table_name='molecules' AND table_type='BASE TABLE') THEN
        ALTER TABLE mol_silver.molecules
            ADD COLUMN IF NOT EXISTS alogp                    NUMERIC,
            ADD COLUMN IF NOT EXISTS hba                      INTEGER,
            ADD COLUMN IF NOT EXISTS hbd                      INTEGER,
            ADD COLUMN IF NOT EXISTS psa                      NUMERIC,
            ADD COLUMN IF NOT EXISTS num_ro5_violations       INTEGER,
            ADD COLUMN IF NOT EXISTS aromatic_rings           INTEGER,
            ADD COLUMN IF NOT EXISTS heavy_atoms              INTEGER,
            ADD COLUMN IF NOT EXISTS exact_mass               NUMERIC,
            ADD COLUMN IF NOT EXISTS isomeric_smiles          TEXT,
            ADD COLUMN IF NOT EXISTS rotatable_bond_count     INTEGER,
            ADD COLUMN IF NOT EXISTS complexity               NUMERIC,
            ADD COLUMN IF NOT EXISTS charge                   INTEGER,
            ADD COLUMN IF NOT EXISTS mesh_headings            JSONB,
            ADD COLUMN IF NOT EXISTS pharmacological_actions  JSONB,
            ADD COLUMN IF NOT EXISTS description              TEXT,
            ADD COLUMN IF NOT EXISTS pharmacodynamics         TEXT,
            ADD COLUMN IF NOT EXISTS drug_categories          JSONB;
    END IF;
END $$;

-- FROM 101: mol_silver.clinical_trials — eligibility, dates, results, oversight
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='mol_silver' AND table_name='clinical_trials' AND table_type='BASE TABLE') THEN
        ALTER TABLE mol_silver.clinical_trials
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
            ADD COLUMN IF NOT EXISTS fda_regulated_drug   BOOLEAN,
            ADD COLUMN IF NOT EXISTS fda_regulated_device BOOLEAN,
            ADD COLUMN IF NOT EXISTS has_dmc              BOOLEAN;
    END IF;
END $$;

-- FROM 101: mol_silver.drug_labels
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='mol_silver' AND table_name='drug_labels' AND table_type='BASE TABLE') THEN
        ALTER TABLE mol_silver.drug_labels
            ADD COLUMN IF NOT EXISTS use_in_specific_populations TEXT,
            ADD COLUMN IF NOT EXISTS pharmacodynamics             TEXT,
            ADD COLUMN IF NOT EXISTS nursing_mothers              TEXT,
            ADD COLUMN IF NOT EXISTS storage_and_handling         TEXT,
            ADD COLUMN IF NOT EXISTS principal_display_panel      TEXT,
            ADD COLUMN IF NOT EXISTS is_original_packager         BOOLEAN,
            ADD COLUMN IF NOT EXISTS spl_set_ids                  JSONB,
            ADD COLUMN IF NOT EXISTS nui                          JSONB;
    END IF;
END $$;

-- FROM 101: mol_silver.adverse_events — FAERS seriousness sub-types
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='mol_silver' AND table_name='adverse_events' AND table_type='BASE TABLE') THEN
        ALTER TABLE mol_silver.adverse_events
            ADD COLUMN IF NOT EXISTS lifethreatening_count INTEGER,
            ADD COLUMN IF NOT EXISTS disabling_count        INTEGER,
            ADD COLUMN IF NOT EXISTS congenital_count       INTEGER,
            ADD COLUMN IF NOT EXISTS other_serious_count    INTEGER;
    END IF;
END $$;

-- FROM 101: mol_silver.publications — Cochrane fields (BASE TABLE only; skip VIEWs)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='mol_silver' AND table_name='publications' AND table_type='BASE TABLE') THEN
        ALTER TABLE mol_silver.publications
            ADD COLUMN IF NOT EXISTS conclusions            TEXT,
            ADD COLUMN IF NOT EXISTS interventions_reviewed JSONB,
            ADD COLUMN IF NOT EXISTS conditions_reviewed    JSONB;
    END IF;
END $$;

-- FROM 101: NEW TABLE mol_silver.drug_pharmacology
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

-- FROM 101: NEW TABLE mol_silver.proteins
CREATE TABLE IF NOT EXISTS mol_silver.proteins (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id          UUID        REFERENCES mol_silver.molecules(molecule_id),
    uniprot_id           TEXT        NOT NULL UNIQUE,
    entry_name           TEXT,
    entry_type           TEXT,
    protein_name         TEXT,
    short_name           TEXT,
    alternative_names    JSONB,
    submission_names     JSONB,
    gene_name            TEXT,
    genes                JSONB,
    organism_scientific  TEXT,
    organism_common      TEXT,
    taxonomy_id          INTEGER,
    lineage              JSONB,
    sequence             TEXT,
    sequence_length      INTEGER,
    molecular_weight     INTEGER,
    sequence_checksum    TEXT,
    comments             JSONB,
    features             JSONB,
    keywords             JSONB,
    go_terms             JSONB,
    annotation_score     NUMERIC,
    cross_references     JSONB,
    secondary_accessions JSONB,
    pdb_structures       JSONB,
    extra_attributes     JSONB,
    source               TEXT,
    source_updated_at    TIMESTAMPTZ,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

-- FROM 101: NEW TABLE mol_silver.research_grants
CREATE TABLE IF NOT EXISTS mol_silver.research_grants (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id           UUID        REFERENCES mol_silver.molecules(molecule_id),
    appl_id               INTEGER,
    project_num           TEXT        NOT NULL UNIQUE,
    study_section         TEXT,
    project_title         TEXT        NOT NULL,
    fiscal_year           INTEGER,
    activity_code         TEXT,
    mechanism_code        TEXT,
    funding_mechanism     TEXT,
    pi_names              JSONB,
    program_officials     JSONB,
    organization_name     TEXT,
    organization_city     TEXT,
    organization_state    TEXT,
    organization_country  TEXT,
    award_amount          NUMERIC,
    total_cost            NUMERIC,
    abstract_text         TEXT,
    terms                 TEXT,
    project_start_date    DATE,
    project_end_date      DATE,
    source                TEXT,
    source_updated_at     TIMESTAMPTZ,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

-- FROM 101: NEW TABLE mol_silver.protein_structures
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

-- FROM 101: NEW TABLE mol_silver.company_financials
CREATE TABLE IF NOT EXISTS mol_silver.company_financials (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    filing_id         TEXT        NOT NULL UNIQUE,
    cik               TEXT        NOT NULL,
    company_name      TEXT,
    filing_type       TEXT,
    filing_date       DATE,
    document_url      TEXT,
    description       TEXT,
    revenue           NUMERIC,
    net_income        NUMERIC,
    total_assets      NUMERIC,
    source            TEXT,
    source_updated_at TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- FROM 103: meta platform tables
-- ============================================================================

-- Move existing raw.* tables to meta.* where they still live in raw.*
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'sync_schedules','ingestion_jobs','silver_transformation_rules',
        'generated_sqlmesh_models','source_identifier_patterns','transformation_templates'
    ] LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='raw' AND table_name=t) THEN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='meta' AND table_name=t) THEN
                EXECUTE format('DROP TABLE raw.%I CASCADE', t);
            ELSE
                EXECUTE format('ALTER TABLE raw.%I SET SCHEMA meta', t);
            END IF;
        END IF;
    END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS meta.pipeline_jobs (
    id            SERIAL PRIMARY KEY,
    job_id        VARCHAR(100) UNIQUE NOT NULL,
    job_type      VARCHAR(100),
    source        VARCHAR(100),
    status        VARCHAR(50)  NOT NULL DEFAULT 'pending',
    started_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ,
    error_message TEXT,
    metadata      JSONB,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_meta_pipeline_jobs_status  ON meta.pipeline_jobs(status);
CREATE INDEX IF NOT EXISTS idx_meta_pipeline_jobs_started ON meta.pipeline_jobs(started_at DESC);

CREATE TABLE IF NOT EXISTS meta.initial_load_state (
    id         SERIAL PRIMARY KEY,
    run_id     VARCHAR(100) UNIQUE NOT NULL,
    state      JSONB        NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.transformation_config (
    id           SERIAL PRIMARY KEY,
    config_key   VARCHAR(255) UNIQUE NOT NULL,
    config_value JSONB        NOT NULL DEFAULT '{}',
    description  TEXT,
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.identifier_types (
    id          SERIAL PRIMARY KEY,
    type_name   VARCHAR(100) UNIQUE NOT NULL,
    domain      VARCHAR(50),
    description TEXT,
    pattern     TEXT,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.source_config (
    id          SERIAL PRIMARY KEY,
    source_name VARCHAR(255) UNIQUE NOT NULL,
    config      JSONB        NOT NULL DEFAULT '{}',
    enabled     BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_meta_source_config_enabled ON meta.source_config(enabled);

CREATE TABLE IF NOT EXISTS meta.field_mappings (
    id            SERIAL PRIMARY KEY,
    source_name   VARCHAR(255) NOT NULL,
    source_field  VARCHAR(255) NOT NULL,
    target_schema VARCHAR(100),
    target_table  VARCHAR(255),
    target_field  VARCHAR(255),
    transform_expr TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(source_name, source_field)
);
CREATE INDEX IF NOT EXISTS idx_meta_field_mappings_source ON meta.field_mappings(source_name);

CREATE TABLE IF NOT EXISTS meta.api_responses (
    id            SERIAL PRIMARY KEY,
    source        VARCHAR(255) NOT NULL,
    endpoint      TEXT,
    status_code   INTEGER,
    response_size BIGINT,
    duration_ms   INTEGER,
    recorded_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_meta_api_responses_source ON meta.api_responses(source);
CREATE INDEX IF NOT EXISTS idx_meta_api_responses_ts     ON meta.api_responses(recorded_at DESC);

-- ============================================================================
-- FROM 105: hcs_raw.hrsa_shortage_areas
-- ============================================================================

CREATE TABLE IF NOT EXISTS hcs_raw.hrsa_shortage_areas (
    id               BIGSERIAL PRIMARY KEY,
    hpsa_id          TEXT,
    hpsa_name        TEXT,
    hpsa_type        TEXT,
    designation_type TEXT,
    state_abbr       TEXT,
    county_name      TEXT,
    hpsa_score       INTEGER,
    designation_date DATE,
    rural_status     TEXT,
    _source_hash     TEXT,
    _fetched_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_hrsa_shortage_state ON hcs_raw.hrsa_shortage_areas(state_abbr);
CREATE INDEX IF NOT EXISTS idx_hrsa_shortage_type  ON hcs_raw.hrsa_shortage_areas(hpsa_type);

-- ============================================================================
-- FROM 107: mol_raw.uspto_patents
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_raw' AND table_name='uspto_patents') THEN
        ALTER TABLE mol_raw.uspto_patents
            ADD COLUMN IF NOT EXISTS patent_type TEXT,
            ADD COLUMN IF NOT EXISTS patent_kind TEXT;
    END IF;
END $$;

-- ============================================================================
-- FROM 108: mol_raw.epo_patents
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_raw' AND table_name='epo_patents') THEN
        ALTER TABLE mol_raw.epo_patents ADD COLUMN IF NOT EXISTS cpc_codes TEXT[];
        CREATE INDEX IF NOT EXISTS idx_epo_cpc ON mol_raw.epo_patents USING GIN(cpc_codes);
    END IF;
END $$;

-- ============================================================================
-- FROM 109: hcs_raw.hrsa_shortage_areas.hpsa_status
-- ============================================================================

ALTER TABLE hcs_raw.hrsa_shortage_areas
    ADD COLUMN IF NOT EXISTS hpsa_status TEXT;

-- ============================================================================
-- FROM 112: mol_raw.openalex_ci extended columns
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_raw' AND table_name='openalex_ci') THEN
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS pmid                          TEXT;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS pmcid                         TEXT;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS mag_id                        TEXT;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS work_type                     TEXT;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS language                      TEXT;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS volume                        TEXT;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS issue                         TEXT;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS first_page                    TEXT;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS last_page                     TEXT;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS topics                        JSONB;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS keywords                      JSONB;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS mesh_terms                    JSONB;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS cited_by_percentile           NUMERIC;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS citation_counts_by_year       JSONB;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS grants                        JSONB;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS referenced_works              JSONB;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS related_works                 JSONB;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS sustainable_development_goals JSONB;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS best_oa_location              JSONB;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS is_retracted                  BOOLEAN;
        ALTER TABLE mol_raw.openalex_ci ADD COLUMN IF NOT EXISTS is_paratext                   BOOLEAN;
        CREATE INDEX IF NOT EXISTS idx_mol_raw_openalex_ci_pmid
            ON mol_raw.openalex_ci(pmid) WHERE pmid IS NOT NULL;
    END IF;
END $$;

-- ============================================================================
-- FROM 115: mol_raw.europepmc_raw
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_raw.europepmc_raw (
    id                  BIGSERIAL   PRIMARY KEY,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_status     INTEGER     NOT NULL DEFAULT 200,
    response_body       JSONB       NOT NULL,
    processed_to_bronze BOOLEAN     NOT NULL DEFAULT FALSE,
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_europepmc_raw_pmid
    ON mol_raw.europepmc_raw((response_body->>'pmid'))
    WHERE response_body->>'pmid' IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_europepmc_raw_loaded_at
    ON mol_raw.europepmc_raw(_loaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_europepmc_raw_processed
    ON mol_raw.europepmc_raw(processed_to_bronze) WHERE NOT processed_to_bronze;

-- ============================================================================
-- FROM 117: hcs_silver agent tables — updated_at + constraint fixes
-- ============================================================================

-- Add updated_at to all 6 agent tables (may be in hcs_silver or hcs_agents)
DO $$
DECLARE s TEXT; t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['service_lines','idn_hierarchy','referral_network',
                              'verified_contacts','staffing_decomposition','equipment_inventory'] LOOP
        FOREACH s IN ARRAY ARRAY['hcs_silver','hcs_agents'] LOOP
            IF EXISTS (SELECT 1 FROM information_schema.tables
                       WHERE table_schema=s AND table_name=t) THEN
                EXECUTE format('ALTER TABLE %I.%I ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()', s, t);
            END IF;
        END LOOP;
    END LOOP;
END $$;

-- Fix service_lines UNIQUE: (npi, service_line, _source_year) → (npi)
DO $$
DECLARE s TEXT;
BEGIN
    FOREACH s IN ARRAY ARRAY['hcs_silver','hcs_agents'] LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=s AND table_name='service_lines') THEN
            -- Drop old composite constraint if present
            PERFORM constraint_name FROM information_schema.table_constraints
            WHERE table_schema=s AND table_name='service_lines'
              AND constraint_type='UNIQUE' AND constraint_name NOT LIKE '%_pkey' AND constraint_name NOT LIKE '%_npi_key';
            IF FOUND THEN
                EXECUTE (SELECT format('ALTER TABLE %I.service_lines DROP CONSTRAINT %I', s, constraint_name)
                         FROM information_schema.table_constraints
                         WHERE table_schema=s AND table_name='service_lines'
                           AND constraint_type='UNIQUE' AND constraint_name NOT LIKE '%_pkey' AND constraint_name NOT LIKE '%_npi_key'
                         LIMIT 1);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints
                           WHERE table_schema=s AND table_name='service_lines' AND constraint_name='service_lines_npi_key') THEN
                EXECUTE format('ALTER TABLE %I.service_lines ADD CONSTRAINT service_lines_npi_key UNIQUE (npi)', s);
            END IF;
        END IF;
    END LOOP;
END $$;

-- Fix idn_hierarchy UNIQUE: (child_npi, parent_organization) → (child_npi)
DO $$
DECLARE s TEXT;
BEGIN
    FOREACH s IN ARRAY ARRAY['hcs_silver','hcs_agents'] LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=s AND table_name='idn_hierarchy') THEN
            PERFORM constraint_name FROM information_schema.table_constraints
            WHERE table_schema=s AND table_name='idn_hierarchy'
              AND constraint_type='UNIQUE' AND constraint_name NOT LIKE '%_pkey' AND constraint_name NOT LIKE '%_child_npi_key';
            IF FOUND THEN
                EXECUTE (SELECT format('ALTER TABLE %I.idn_hierarchy DROP CONSTRAINT %I', s, constraint_name)
                         FROM information_schema.table_constraints
                         WHERE table_schema=s AND table_name='idn_hierarchy'
                           AND constraint_type='UNIQUE' AND constraint_name NOT LIKE '%_pkey' AND constraint_name NOT LIKE '%_child_npi_key'
                         LIMIT 1);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints
                           WHERE table_schema=s AND table_name='idn_hierarchy' AND constraint_name='idn_hierarchy_child_npi_key') THEN
                EXECUTE format('ALTER TABLE %I.idn_hierarchy ADD CONSTRAINT idn_hierarchy_child_npi_key UNIQUE (child_npi)', s);
            END IF;
        END IF;
    END LOOP;
END $$;

-- Add relationship_strength to referral_network and inferred_equipment to equipment_inventory
DO $$
DECLARE s TEXT;
BEGIN
    FOREACH s IN ARRAY ARRAY['hcs_silver','hcs_agents'] LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=s AND table_name='referral_network') THEN
            EXECUTE format('ALTER TABLE %I.referral_network ADD COLUMN IF NOT EXISTS relationship_strength TEXT', s);
        END IF;
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=s AND table_name='equipment_inventory') THEN
            EXECUTE format('ALTER TABLE %I.equipment_inventory ADD COLUMN IF NOT EXISTS inferred_equipment TEXT', s);
        END IF;
    END LOOP;
END $$;

-- FROM 117: hcs_raw.cms_nppes additional practice-location columns
ALTER TABLE hcs_raw.cms_nppes
    ADD COLUMN IF NOT EXISTS provider_business_mailing_address_city_name TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_mailing_address_state_name TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_mailing_address_postal_code TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_telephone_number TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_fax_number TEXT,
    ADD COLUMN IF NOT EXISTS provider_first_line_business_practice_location_address TEXT,
    ADD COLUMN IF NOT EXISTS provider_second_line_business_practice_location_address TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_city_name TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_postal_code TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_country_code TEXT,
    ADD COLUMN IF NOT EXISTS provider_credential_text TEXT,
    ADD COLUMN IF NOT EXISTS provider_first_line_business_mailing_address TEXT,
    ADD COLUMN IF NOT EXISTS provider_second_line_business_mailing_address TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_practice_location_address_state_name TEXT,
    ADD COLUMN IF NOT EXISTS npi_deactivation_date DATE,
    ADD COLUMN IF NOT EXISTS npi_reactivation_date DATE;

-- FROM 117: NEW TABLE hcs_raw.cms_physician_puf_services
CREATE TABLE IF NOT EXISTS hcs_raw.cms_physician_puf_services (
    id                           BIGSERIAL PRIMARY KEY,
    npi                          TEXT NOT NULL,
    hcpcs_code                   TEXT NOT NULL,
    hcpcs_description            TEXT,
    hcpcs_drug_ind               TEXT,
    place_of_service             TEXT,
    line_srvc_cnt                NUMERIC(18,2),
    bene_unique_cnt              INTEGER,
    bene_day_srvc_cnt            INTEGER,
    average_medicare_allowed_amt NUMERIC(18,2),
    average_submitted_chrg_amt   NUMERIC(18,2),
    average_medicare_payment_amt NUMERIC(18,2),
    average_medicare_stnd_amt    NUMERIC(18,2),
    _source_year                 INTEGER NOT NULL,
    _source_hash                 TEXT NOT NULL,
    _source_file                 TEXT,
    _loaded_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, hcpcs_code, place_of_service, _source_year)
);

-- FROM 117: NEW TABLE hcs_raw.cms_cost_reports_puf_lines
CREATE TABLE IF NOT EXISTS hcs_raw.cms_cost_reports_puf_lines (
    id                    BIGSERIAL PRIMARY KEY,
    provider_id           TEXT NOT NULL,
    facility_type         TEXT,
    line_item_code        TEXT NOT NULL,
    line_item_description TEXT,
    reported_hours_fte    NUMERIC(12,2),
    total_salaries        NUMERIC(18,2),
    source_year           INTEGER,
    _source_year          INTEGER NOT NULL,
    _source_hash          TEXT NOT NULL,
    _source_file          TEXT,
    _loaded_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, line_item_code, _source_year)
);

-- FROM 117: Recreate CMS PUF staging tables with correct schemas
-- OPERATIONAL NOTE: The 13 tables below are dropped and recreated to apply column-level schema
-- corrections that cannot be done with ADD COLUMN (wrong types/constraints in the baselined DDL).
-- These are raw staging tables with no FK dependents. Active ingestion data will be lost and
-- must be re-ingested by the corresponding CronJobs after deployment. Re-ingest is automatic
-- on the next CronJob run; all data is recoverable from upstream CMS sources.
-- Tables affected: cms_part_d_spending, cms_part_b_spending, cms_medicare_advantage,
--   cms_medicaid_drug_spending, cms_mental_health_puf, cms_opioid_puf, cms_ordering_providers,
--   cms_outpatient_puf, cms_referring_providers, cms_telehealth_puf, cms_geographic_variation,
--   cms_chronic_conditions, cms_dual_eligible, cms_enrollment_puf, cms_claim_type_puf,
--   cms_utilization_puf, cms_cost_reports_puf

DROP TABLE IF EXISTS hcs_raw.cms_part_d_spending CASCADE;
CREATE TABLE hcs_raw.cms_part_d_spending (
    id BIGSERIAL PRIMARY KEY,
    brnd_name TEXT, gnrc_name TEXT, tot_mftr INTEGER,
    tot_spndng NUMERIC(18,2), tot_dsg_unts NUMERIC(18,2),
    tot_clms BIGINT, tot_benes INTEGER,
    avg_spnd_per_dsg_unt_wghtd NUMERIC(18,2),
    avg_spnd_per_clm NUMERIC(18,2), avg_spnd_per_bene NUMERIC(18,2),
    outlier_flag TEXT,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (_source_hash, gnrc_name, _source_year)
);

DROP TABLE IF EXISTS hcs_raw.cms_part_b_spending CASCADE;
CREATE TABLE hcs_raw.cms_part_b_spending (
    id BIGSERIAL PRIMARY KEY,
    hcpcs_cd TEXT, hcpcs_desc TEXT,
    tot_mftr INTEGER, mftr_name TEXT,
    tot_spndng NUMERIC(18,2), tot_dsg_unts NUMERIC(18,2),
    tot_benes INTEGER, tot_clms BIGINT,
    avg_spnd_per_dsg_unt NUMERIC(18,2),
    avg_spnd_per_clm NUMERIC(18,2), avg_spnd_per_bene NUMERIC(18,2),
    outlier_flag TEXT,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (_source_hash, hcpcs_cd, _source_year)
);

DROP TABLE IF EXISTS hcs_raw.cms_medicare_advantage CASCADE;
CREATE TABLE hcs_raw.cms_medicare_advantage (
    id BIGSERIAL PRIMARY KEY,
    contract_id TEXT, organization_name TEXT, organization_type TEXT,
    plan_id TEXT, plan_name TEXT, segment_id TEXT,
    enrollment_data_period TEXT,
    fips_cd TEXT, state_fips TEXT, county_fips TEXT,
    enrollment INTEGER,
    avg_age NUMERIC(5,2), pct_female NUMERIC(5,2),
    avg_risk_score NUMERIC(8,4), ma_participation_rate NUMERIC(5,4),
    star_rating NUMERIC(4,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_medicaid_drug_spending CASCADE;
CREATE TABLE hcs_raw.cms_medicaid_drug_spending (
    id BIGSERIAL PRIMARY KEY,
    brnd_name TEXT, gnrc_name TEXT,
    tot_mftr INTEGER, util_type TEXT,
    tot_spndng NUMERIC(18,2),
    medicaid_spndng_per_dosage_unit NUMERIC(18,4),
    medicaid_spndng_per_prescription NUMERIC(18,4),
    unit_type TEXT, tot_dosage_units NUMERIC(18,2),
    tot_prescriptions INTEGER, tot_benes INTEGER,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_mental_health_puf CASCADE;
CREATE TABLE hcs_raw.cms_mental_health_puf (
    id BIGSERIAL PRIMARY KEY,
    npi TEXT, provider_last_org_name TEXT, provider_first_name TEXT,
    provider_city TEXT, provider_state TEXT, provider_zip5 TEXT,
    provider_type TEXT, hcpcs_cd TEXT, hcpcs_desc TEXT,
    mh_srvc_ind TEXT,
    tot_benes INTEGER, tot_srvcs INTEGER,
    tot_mdcr_alowd_amt NUMERIC(18,2),
    avg_mdcr_alowd_amt NUMERIC(18,2),
    avg_mdcr_pymt_amt NUMERIC(18,2),
    avg_mdcr_stdzd_amt NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_opioid_puf CASCADE;
CREATE TABLE hcs_raw.cms_opioid_puf (
    id BIGSERIAL PRIMARY KEY,
    prscrbr_npi TEXT, prscrbr_last_org_name TEXT, prscrbr_first_name TEXT,
    prscrbr_city TEXT, prscrbr_state_abrvtn TEXT, prscrbr_state_fips TEXT,
    prscrbr_type TEXT, prscrbr_type_src TEXT,
    brnd_name TEXT, gnrc_name TEXT,
    opioid_drug_flag TEXT, la_opioid_drug_flag TEXT,
    tot_clms INTEGER, tot_30day_fills NUMERIC(18,2),
    tot_day_suply BIGINT, tot_drug_cst NUMERIC(18,2),
    tot_benes INTEGER,
    opioid_clms INTEGER, opioid_benes INTEGER,
    la_opioid_clms INTEGER, la_opioid_benes INTEGER,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_ordering_providers CASCADE;
CREATE TABLE hcs_raw.cms_ordering_providers (
    id BIGSERIAL PRIMARY KEY,
    rndrng_npi TEXT, rndrng_prvdr_last_org_name TEXT,
    rndrng_prvdr_first_name TEXT, rndrng_prvdr_city TEXT,
    rndrng_prvdr_state_abrvtn TEXT, rndrng_prvdr_zip5 TEXT,
    rndrng_prvdr_type TEXT,
    rfrd_npi TEXT, rfrd_prvdr_last_org_name TEXT, rfrd_prvdr_type TEXT,
    tot_srvcs INTEGER, tot_benes INTEGER,
    tot_mdcr_alowd_amt NUMERIC(18,2), tot_mdcr_pymt_amt NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_outpatient_puf CASCADE;
CREATE TABLE hcs_raw.cms_outpatient_puf (
    id BIGSERIAL PRIMARY KEY,
    provider_id TEXT, provider_name TEXT, provider_street_address TEXT,
    provider_city TEXT, provider_state TEXT, provider_state_fips TEXT,
    provider_zip_code TEXT, provider_ruca TEXT,
    apc TEXT, apc_desc TEXT,
    total_services INTEGER, bene_cnt INTEGER, comp_asgn_pymt_cnt INTEGER,
    average_estimated_submitted_charges NUMERIC(18,2),
    average_medicare_allowed_amt NUMERIC(18,2),
    average_total_payments NUMERIC(18,2),
    average_medicare_payments NUMERIC(18,2),
    average_medicare_stnd_amt NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (_source_hash, provider_id, apc, _source_year)
);

DROP TABLE IF EXISTS hcs_raw.cms_referring_providers CASCADE;
CREATE TABLE hcs_raw.cms_referring_providers (
    id BIGSERIAL PRIMARY KEY,
    rndrng_npi TEXT, rndrng_prvdr_last_org_name TEXT,
    rndrng_prvdr_first_name TEXT, rndrng_prvdr_city TEXT,
    rndrng_prvdr_state_abrvtn TEXT, rndrng_prvdr_zip5 TEXT,
    rndrng_prvdr_type TEXT,
    rfrd_npi TEXT, rfrd_prvdr_last_org_name TEXT, rfrd_prvdr_type TEXT,
    tot_srvcs INTEGER, tot_benes INTEGER,
    tot_mdcr_alowd_amt NUMERIC(18,2), tot_mdcr_pymt_amt NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_telehealth_puf CASCADE;
CREATE TABLE hcs_raw.cms_telehealth_puf (
    id BIGSERIAL PRIMARY KEY,
    npi TEXT, provider_last_org_name TEXT, provider_first_name TEXT,
    provider_city TEXT, provider_state TEXT, provider_zip5 TEXT,
    provider_type TEXT, hcpcs_cd TEXT, hcpcs_desc TEXT,
    th_srvc_ind TEXT,
    tot_benes INTEGER, tot_srvcs INTEGER,
    tot_mdcr_alowd_amt NUMERIC(18,2),
    avg_mdcr_alowd_amt NUMERIC(18,2),
    avg_mdcr_pymt_amt NUMERIC(18,2),
    avg_mdcr_stdzd_amt NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_geographic_variation CASCADE;
CREATE TABLE hcs_raw.cms_geographic_variation (
    id BIGSERIAL PRIMARY KEY,
    bene_geo_lvl TEXT, bene_geo_desc TEXT, bene_geo_cd TEXT,
    bene_age_lvl TEXT, bene_demo_lvl TEXT, bene_demo_desc TEXT,
    bene_mcc_lvl TEXT, year INTEGER,
    tot_benes INTEGER,
    ip_cvrd_stays_per_1000_benes NUMERIC(10,4),
    er_visits_per_1000_benes NUMERIC(10,4),
    hosp_readmsn_rate NUMERIC(10,4),
    acute_hosp_readmsn_rate NUMERIC(10,4),
    tot_mdcr_stdzd_pymt_pc NUMERIC(18,2),
    tot_mdcr_stdzd_pymt_pct_chg NUMERIC(10,4),
    tot_mdcr_pymt_pc NUMERIC(18,2),
    tot_mdcr_alowd_amt_pc NUMERIC(18,2),
    ma_prtcptn_rate NUMERIC(10,4),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_chronic_conditions CASCADE;
CREATE TABLE hcs_raw.cms_chronic_conditions (
    id BIGSERIAL PRIMARY KEY,
    bene_geo_lvl TEXT, bene_geo_desc TEXT, bene_geo_cd TEXT,
    bene_age_lvl TEXT, bene_demo_lvl TEXT, bene_demo_desc TEXT,
    bene_cond TEXT,
    prvlnc NUMERIC(10,4),
    tot_mdcr_stdzd_pymt_pc NUMERIC(18,2),
    tot_mdcr_pymt_pc NUMERIC(18,2),
    hosp_readmsn_rate NUMERIC(10,4),
    ed_visits_per_1000_benes NUMERIC(10,4),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_dual_eligible CASCADE;
CREATE TABLE hcs_raw.cms_dual_eligible (
    id BIGSERIAL PRIMARY KEY,
    state_cd TEXT, state_name TEXT,
    dual_elgbl_lvl TEXT, dual_elgbl_desc TEXT,
    tot_benes INTEGER, ffs_benes INTEGER, ma_benes INTEGER,
    dual_elgbl_full_benes INTEGER, dual_elgbl_prtl_benes INTEGER,
    non_dual_benes INTEGER, lis_benes INTEGER,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_enrollment_puf CASCADE;
CREATE TABLE hcs_raw.cms_enrollment_puf (
    id BIGSERIAL PRIMARY KEY,
    state_cd TEXT, county_cd TEXT, county_desc TEXT,
    bene_demo_lvl TEXT, bene_demo_desc TEXT, bene_age_lvl TEXT,
    tot_benes INTEGER, orgnl_mdcr_benes INTEGER,
    ma_benes INTEGER, esrd_benes INTEGER, dsbl_benes INTEGER,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_claim_type_puf CASCADE;
CREATE TABLE hcs_raw.cms_claim_type_puf (
    id BIGSERIAL PRIMARY KEY,
    bene_geo_lvl TEXT, bene_geo_desc TEXT,
    clm_type TEXT, clm_type_desc TEXT,
    tot_clms BIGINT, tot_benes INTEGER,
    tot_mdcr_pymt_amt NUMERIC(18,2),
    avg_mdcr_pymt_amt NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_utilization_puf CASCADE;
CREATE TABLE hcs_raw.cms_utilization_puf (
    id BIGSERIAL PRIMARY KEY,
    bene_geo_lvl TEXT, bene_geo_desc TEXT, bene_geo_cd TEXT,
    bene_age_lvl TEXT, bene_demo_lvl TEXT, bene_demo_desc TEXT,
    srvcs_per_bene NUMERIC(10,4),
    ip_cvrd_stays_per_1000_benes NUMERIC(10,4),
    avg_ip_los NUMERIC(10,2),
    er_visits_per_1000_benes NUMERIC(10,4),
    phy_visits_per_bene NUMERIC(10,4),
    tot_mdcr_pymt_pc NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_cost_reports_puf CASCADE;
CREATE TABLE hcs_raw.cms_cost_reports_puf (
    id                       BIGSERIAL PRIMARY KEY,
    provider_id              TEXT NOT NULL,
    hospital_name            TEXT,
    city                     TEXT,
    state                    TEXT,
    zip_code                 TEXT,
    fiscal_year_begin        DATE,
    fiscal_year_end          DATE,
    total_beds               INTEGER,
    total_discharges         INTEGER,
    net_patient_revenue      NUMERIC(18,2),
    total_operating_expenses NUMERIC(18,2),
    operating_margin         NUMERIC(10,4),
    _source_year             INTEGER NOT NULL,
    _source_hash             TEXT NOT NULL,
    _source_file             TEXT,
    _loaded_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, fiscal_year_begin, _source_year)
);

-- FROM 117: cms_open_payments additional columns
ALTER TABLE hcs_raw.cms_open_payments
    ADD COLUMN IF NOT EXISTS number_of_payments_included_in_total_amount INTEGER,
    ADD COLUMN IF NOT EXISTS form_of_payment_or_transfer_of_value TEXT,
    ADD COLUMN IF NOT EXISTS payment_publication_date DATE,
    ADD COLUMN IF NOT EXISTS record_id TEXT,
    ADD COLUMN IF NOT EXISTS program_year INTEGER,
    ADD COLUMN IF NOT EXISTS name_of_drug_or_biological_or_device_or_medical_supply_1 TEXT,
    ADD COLUMN IF NOT EXISTS name_of_drug_or_biological_or_device_or_medical_supply_2 TEXT,
    ADD COLUMN IF NOT EXISTS name_of_drug_or_biological_or_device_or_medical_supply_3 TEXT,
    ADD COLUMN IF NOT EXISTS name_of_drug_or_biological_or_device_or_medical_supply_4 TEXT,
    ADD COLUMN IF NOT EXISTS name_of_drug_or_biological_or_device_or_medical_supply_5 TEXT,
    ADD COLUMN IF NOT EXISTS associated_drug_or_biological_ndc_1 TEXT,
    ADD COLUMN IF NOT EXISTS associated_drug_or_biological_ndc_2 TEXT,
    ADD COLUMN IF NOT EXISTS associated_drug_or_biological_ndc_3 TEXT,
    ADD COLUMN IF NOT EXISTS associated_drug_or_biological_ndc_4 TEXT,
    ADD COLUMN IF NOT EXISTS associated_drug_or_biological_ndc_5 TEXT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='hcs_raw' AND table_name='cms_open_payments'
                   AND column_name='drug_name_1_normalized') THEN
        ALTER TABLE hcs_raw.cms_open_payments
            ADD COLUMN drug_name_1_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_1,''), '[^a-z0-9 ]', '', 'g'))) STORED,
            ADD COLUMN drug_name_2_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_2,''), '[^a-z0-9 ]', '', 'g'))) STORED,
            ADD COLUMN drug_name_3_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_3,''), '[^a-z0-9 ]', '', 'g'))) STORED,
            ADD COLUMN drug_name_4_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_4,''), '[^a-z0-9 ]', '', 'g'))) STORED,
            ADD COLUMN drug_name_5_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_5,''), '[^a-z0-9 ]', '', 'g'))) STORED;
    END IF;
END $$;

-- FROM 117: cms_inpatient_puf, cms_physician_puf extended columns
ALTER TABLE hcs_raw.cms_inpatient_puf
    ADD COLUMN IF NOT EXISTS drg_cd             TEXT,
    ADD COLUMN IF NOT EXISTS provider_state_fips TEXT,
    ADD COLUMN IF NOT EXISTS provider_ruca       TEXT;

ALTER TABLE hcs_raw.cms_physician_puf
    ADD COLUMN IF NOT EXISTS nppes_provider_street1     TEXT,
    ADD COLUMN IF NOT EXISTS nppes_provider_street2     TEXT,
    ADD COLUMN IF NOT EXISTS nppes_provider_state_fips  TEXT,
    ADD COLUMN IF NOT EXISTS nppes_provider_ruca        TEXT,
    ADD COLUMN IF NOT EXISTS nppes_provider_country     TEXT;

-- FROM 117: cms_hospital_general_info column renames + extras
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='hcs_raw' AND table_name='cms_hospital_general_info' AND column_name='city') THEN
        ALTER TABLE hcs_raw.cms_hospital_general_info RENAME COLUMN city TO city_town;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='hcs_raw' AND table_name='cms_hospital_general_info' AND column_name='county_name') THEN
        ALTER TABLE hcs_raw.cms_hospital_general_info RENAME COLUMN county_name TO county_parish;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='hcs_raw' AND table_name='cms_hospital_general_info' AND column_name='phone_number') THEN
        ALTER TABLE hcs_raw.cms_hospital_general_info RENAME COLUMN phone_number TO telephone_number;
    END IF;
END $$;
ALTER TABLE hcs_raw.cms_hospital_general_info
    ADD COLUMN IF NOT EXISTS meets_criteria_for_birthing_friendly_designation TEXT,
    ADD COLUMN IF NOT EXISTS hospital_overall_rating_footnote TEXT;

-- FROM 117: Move hcs_silver agent tables to hcs_agents schema
CREATE SCHEMA IF NOT EXISTS hcs_agents;
CREATE SCHEMA IF NOT EXISTS mol_agents;
CREATE SCHEMA IF NOT EXISTS agents;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['service_lines','idn_hierarchy','referral_network',
                              'verified_contacts','staffing_decomposition','equipment_inventory'] LOOP
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='hcs_silver' AND table_name=t) THEN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='hcs_agents' AND table_name=t) THEN
                EXECUTE format('DROP TABLE hcs_silver.%I CASCADE', t);
            ELSE
                EXECUTE format('ALTER TABLE hcs_silver.%I SET SCHEMA hcs_agents', t);
            END IF;
        END IF;
    END LOOP;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_silver' AND table_name='publication_evidence_staging') THEN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_agents' AND table_name='publication_evidence_staging') THEN
            DROP TABLE mol_silver.publication_evidence_staging CASCADE;
        ELSE
            ALTER TABLE mol_silver.publication_evidence_staging SET SCHEMA mol_agents;
        END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='mol_silver' AND table_name='agent_quarantine') THEN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='agents' AND table_name='agent_quarantine') THEN
            DROP TABLE mol_silver.agent_quarantine CASCADE;
        ELSE
            ALTER TABLE mol_silver.agent_quarantine SET SCHEMA agents;
        END IF;
    END IF;
END $$;

GRANT USAGE ON SCHEMA hcs_agents TO web_anon;
GRANT USAGE ON SCHEMA mol_agents  TO web_anon;
GRANT USAGE ON SCHEMA agents      TO web_anon;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_agents TO web_anon;
GRANT SELECT ON ALL TABLES IN SCHEMA mol_agents  TO web_anon;
GRANT SELECT ON ALL TABLES IN SCHEMA agents      TO web_anon;

-- ============================================================================
-- FROM 121: mol_raw tables for 7 new molecule sources
-- ============================================================================

CREATE TABLE IF NOT EXISTS mol_raw.ema (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint VARCHAR(500) NOT NULL DEFAULT 'ema',
    api_version VARCHAR(20), request_params JSONB, request_headers JSONB,
    response_status INTEGER NOT NULL DEFAULT 200, response_headers JSONB,
    response_body JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash VARCHAR(64), response_size_bytes INTEGER, response_time_ms INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false, processed_at TIMESTAMPTZ, processing_error TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(), source_id VARCHAR(50) NOT NULL DEFAULT 'ema'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_ema_request_id ON mol_raw.ema(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ema_ts ON mol_raw.ema(ingested_at);

CREATE TABLE IF NOT EXISTS mol_raw.orange_book (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint VARCHAR(500) NOT NULL DEFAULT 'orange_book',
    api_version VARCHAR(20), request_params JSONB, request_headers JSONB,
    response_status INTEGER NOT NULL DEFAULT 200, response_headers JSONB,
    response_body JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash VARCHAR(64), response_size_bytes INTEGER, response_time_ms INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false, processed_at TIMESTAMPTZ, processing_error TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(), source_id VARCHAR(50) NOT NULL DEFAULT 'orange_book'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_orange_book_request_id ON mol_raw.orange_book(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_orange_book_ts ON mol_raw.orange_book(ingested_at);

CREATE TABLE IF NOT EXISTS mol_raw.dailymed (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint VARCHAR(500) NOT NULL DEFAULT 'dailymed',
    api_version VARCHAR(20), request_params JSONB, request_headers JSONB,
    response_status INTEGER NOT NULL DEFAULT 200, response_headers JSONB,
    response_body JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash VARCHAR(64), response_size_bytes INTEGER, response_time_ms INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false, processed_at TIMESTAMPTZ, processing_error TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(), source_id VARCHAR(50) NOT NULL DEFAULT 'dailymed'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_dailymed_request_id ON mol_raw.dailymed(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_dailymed_ts ON mol_raw.dailymed(ingested_at);

CREATE TABLE IF NOT EXISTS mol_raw.fda_drugs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint VARCHAR(500) NOT NULL DEFAULT 'fda_drugs',
    api_version VARCHAR(20), request_params JSONB, request_headers JSONB,
    response_status INTEGER NOT NULL DEFAULT 200, response_headers JSONB,
    response_body JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash VARCHAR(64), response_size_bytes INTEGER, response_time_ms INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false, processed_at TIMESTAMPTZ, processing_error TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(), source_id VARCHAR(50) NOT NULL DEFAULT 'fda_drugs'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_fda_drugs_request_id ON mol_raw.fda_drugs(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_fda_drugs_ts ON mol_raw.fda_drugs(ingested_at);

CREATE TABLE IF NOT EXISTS mol_raw.ttd (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint VARCHAR(500) NOT NULL DEFAULT 'ttd',
    api_version VARCHAR(20), request_params JSONB, request_headers JSONB,
    response_status INTEGER NOT NULL DEFAULT 200, response_headers JSONB,
    response_body JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash VARCHAR(64), response_size_bytes INTEGER, response_time_ms INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false, processed_at TIMESTAMPTZ, processing_error TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(), source_id VARCHAR(50) NOT NULL DEFAULT 'ttd'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_ttd_request_id ON mol_raw.ttd(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_ttd_ts ON mol_raw.ttd(ingested_at);

CREATE TABLE IF NOT EXISTS mol_raw.imgt (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint VARCHAR(500) NOT NULL DEFAULT 'imgt',
    api_version VARCHAR(20), request_params JSONB, request_headers JSONB,
    response_status INTEGER NOT NULL DEFAULT 200, response_headers JSONB,
    response_body JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash VARCHAR(64), response_size_bytes INTEGER, response_time_ms INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false, processed_at TIMESTAMPTZ, processing_error TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(), source_id VARCHAR(50) NOT NULL DEFAULT 'imgt'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_imgt_request_id ON mol_raw.imgt(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_imgt_ts ON mol_raw.imgt(ingested_at);

CREATE TABLE IF NOT EXISTS mol_raw.cdc_vaccines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id VARCHAR(100) NOT NULL DEFAULT gen_random_uuid()::text,
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    api_endpoint VARCHAR(500) NOT NULL DEFAULT 'cdc_vaccines',
    api_version VARCHAR(20), request_params JSONB, request_headers JSONB,
    response_status INTEGER NOT NULL DEFAULT 200, response_headers JSONB,
    response_body JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body_hash VARCHAR(64), response_size_bytes INTEGER, response_time_ms INTEGER,
    processed_to_bronze BOOLEAN DEFAULT false, processed_at TIMESTAMPTZ, processing_error TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(), source_id VARCHAR(50) NOT NULL DEFAULT 'cdc_vaccines'
);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_cdc_vaccines_request_id ON mol_raw.cdc_vaccines(request_id);
CREATE INDEX IF NOT EXISTS idx_mol_raw_cdc_vaccines_ts ON mol_raw.cdc_vaccines(ingested_at);

INSERT INTO meta.data_sources (source_name, source_type, source_url, description, refresh_frequency, is_active)
VALUES ('ema', 'api', 'https://www.ema.europa.eu', 'EMA European Public Assessment Reports', 'monthly', TRUE)
ON CONFLICT (source_name) DO UPDATE
    SET is_active=EXCLUDED.is_active, source_url=EXCLUDED.source_url,
        description=EXCLUDED.description, refresh_frequency=EXCLUDED.refresh_frequency;

DO $$
BEGIN
    RAISE NOTICE 'Migration 136 complete: applied all schema drift from baselined migrations 100-125.';
END $$;
