-- Migration 085: CMS PUF & Platform Data Reconciliation
-- Feature: 019-cms-puf-platform-reconciliation
-- Date: 2026-03-27
--
-- Delta-only against main-branch schema as of migration 084.
-- All object creation uses IF NOT EXISTS for idempotency.
-- Run: doppler run -- python -m dk_data.scripts.run_migration src/dk_data/sql/migrations/085_cms_puf_platform_reconciliation.sql
--
-- ROLLBACK: see 085_rollback.sql

BEGIN;

-- ============================================================================
-- 1. HCS SCHEMA CREATION
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS hcs_raw;
CREATE SCHEMA IF NOT EXISTS hcs_bronze;
CREATE SCHEMA IF NOT EXISTS hcs_silver;
CREATE SCHEMA IF NOT EXISTS hcs_gold;

COMMENT ON SCHEMA hcs_raw    IS 'Healthcare System raw ingestion tables (019-cms-puf-platform-reconciliation)';
COMMENT ON SCHEMA hcs_bronze IS 'Healthcare System bronze normalized tables (SQLMesh managed)';
COMMENT ON SCHEMA hcs_silver IS 'Healthcare System silver enriched tables (SQLMesh + agent managed)';
COMMENT ON SCHEMA hcs_gold   IS 'Healthcare System gold analytical views (SQLMesh managed)';

-- ============================================================================
-- 2. HCS_RAW TABLES — 7 CORE CMS PUF SOURCES
-- ============================================================================

CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_d_spending (
    id                          BIGSERIAL PRIMARY KEY,
    -- Drug identifiers
    brnd_name                   TEXT,
    gnrc_name                   TEXT,
    tot_mftr                    INTEGER,
    -- Spending metrics
    tot_spndng                  NUMERIC(18,2),
    tot_dsg_unts                NUMERIC(18,2),
    tot_clms                    BIGINT,
    tot_benes                   INTEGER,
    -- Cost per unit averages
    avg_spnd_per_dsg_unt_wghtd  NUMERIC(18,2),
    avg_spnd_per_clm            NUMERIC(18,2),
    avg_spnd_per_bene           NUMERIC(18,2),
    outlier_flag                TEXT,
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (_source_hash, gnrc_name, _source_year)
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_part_b_spending (
    id                          BIGSERIAL PRIMARY KEY,
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    tot_mftr                    INTEGER,
    mftr_name                   TEXT,
    -- Spending metrics
    tot_spndng                  NUMERIC(18,2),
    tot_dsg_unts                NUMERIC(18,2),
    tot_benes                   INTEGER,
    tot_clms                    BIGINT,
    -- Cost per unit averages
    avg_spnd_per_dsg_unt        NUMERIC(18,2),
    avg_spnd_per_clm            NUMERIC(18,2),
    avg_spnd_per_bene           NUMERIC(18,2),
    outlier_flag                TEXT,
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (_source_hash, hcpcs_cd, _source_year)
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_open_payments (
    id                                  BIGSERIAL PRIMARY KEY,
    -- Physician identifiers
    covered_recipient_type              TEXT,
    physician_profile_id                TEXT,
    physician_first_name                TEXT,
    physician_last_name                 TEXT,
    physician_specialty                 TEXT,
    -- Company/payer
    applicable_manufacturer_or_gpo_name TEXT,
    -- Payment details
    total_amount_of_payment_usdollars   NUMERIC(18,2),
    date_of_payment                     DATE,
    number_of_payments_included_in_total_amount INTEGER,
    form_of_payment_or_transfer_of_value TEXT,
    nature_of_payment_or_transfer_of_value TEXT,
    -- Location
    recipient_city                      TEXT,
    recipient_state                     TEXT,
    recipient_zip_code                  TEXT,
    -- Publication / program metadata
    payment_publication_date            DATE,
    record_id                           TEXT,
    program_year                        INTEGER,
    -- Drug/device associations (up to 5 per payment record)
    name_of_drug_or_biological_or_device_or_medical_supply_1 TEXT,
    name_of_drug_or_biological_or_device_or_medical_supply_2 TEXT,
    name_of_drug_or_biological_or_device_or_medical_supply_3 TEXT,
    name_of_drug_or_biological_or_device_or_medical_supply_4 TEXT,
    name_of_drug_or_biological_or_device_or_medical_supply_5 TEXT,
    associated_drug_or_biological_ndc_1 TEXT,
    associated_drug_or_biological_ndc_2 TEXT,
    associated_drug_or_biological_ndc_3 TEXT,
    associated_drug_or_biological_ndc_4 TEXT,
    associated_drug_or_biological_ndc_5 TEXT,
    -- Pre-normalized drug names (GENERATED ALWAYS — enables molecule linkage)
    drug_name_1_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_1,''), '[^a-z0-9 ]', '', 'g'))) STORED,
    drug_name_2_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_2,''), '[^a-z0-9 ]', '', 'g'))) STORED,
    drug_name_3_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_3,''), '[^a-z0-9 ]', '', 'g'))) STORED,
    drug_name_4_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_4,''), '[^a-z0-9 ]', '', 'g'))) STORED,
    drug_name_5_normalized TEXT GENERATED ALWAYS AS (lower(regexp_replace(coalesce(name_of_drug_or_biological_or_device_or_medical_supply_5,''), '[^a-z0-9 ]', '', 'g'))) STORED,
    -- Metadata
    _source_year                        INTEGER NOT NULL,
    _source_hash                        TEXT NOT NULL,
    _source_file                        TEXT,
    _loaded_at                          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_nppes (
    id                          BIGSERIAL PRIMARY KEY,
    npi                         TEXT NOT NULL,
    entity_type_code            TEXT,
    -- Provider names
    provider_last_name          TEXT,
    provider_first_name         TEXT,
    provider_organization_name  TEXT,
    provider_credential_text    TEXT,
    -- Mailing address
    provider_first_line_business_mailing_address    TEXT,
    provider_second_line_business_mailing_address   TEXT,
    provider_business_mailing_address_city_name     TEXT,
    provider_business_mailing_address_state_name    TEXT,
    provider_business_mailing_address_postal_code   TEXT,
    provider_business_mailing_address_telephone_number TEXT,
    -- Practice location address
    provider_first_line_business_practice_location_address  TEXT,
    provider_second_line_business_practice_location_address TEXT,
    provider_business_practice_location_address_city_name   TEXT,
    provider_business_practice_location_address_state_name  TEXT,
    provider_business_practice_location_address_postal_code TEXT,
    provider_business_practice_location_address_country_code TEXT,
    provider_business_practice_location_address_telephone_number TEXT,
    provider_business_practice_location_address_fax_number  TEXT,
    -- Taxonomy/specialty
    healthcare_provider_taxonomy_code_1             TEXT,
    healthcare_provider_taxonomy_code_2             TEXT,
    -- Deactivation status
    npi_deactivation_date                           DATE,
    npi_reactivation_date                           DATE,
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, _source_year)
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
    id                          BIGSERIAL PRIMARY KEY,
    npi                         TEXT,
    nppes_provider_last_org_name TEXT,
    nppes_provider_first_name   TEXT,
    nppes_provider_mi           TEXT,
    nppes_credentials           TEXT,
    nppes_provider_gender       TEXT,
    nppes_entity_code           TEXT,
    nppes_provider_street1      TEXT,
    nppes_provider_street2      TEXT,
    nppes_provider_city         TEXT,
    nppes_provider_state        TEXT,
    nppes_provider_state_fips   TEXT,
    nppes_provider_zip          TEXT,
    nppes_provider_ruca         TEXT,
    nppes_provider_country      TEXT,
    provider_type               TEXT,
    medicare_participation_indicator TEXT,
    number_of_hcpcs             INTEGER,
    total_services              NUMERIC(18,2),
    total_unique_benes          INTEGER,
    total_submitted_chrg_amt    NUMERIC(18,2),
    total_medicare_allowed_amt  NUMERIC(18,2),
    total_medicare_payment_amt  NUMERIC(18,2),
    total_medicare_stnd_amt     NUMERIC(18,2),
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
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
-- 3. HCS_RAW TABLES — 21 ADDITIONAL CMS PUF SOURCES
-- ============================================================================

CREATE TABLE IF NOT EXISTS hcs_raw.cms_medicare_advantage (
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

CREATE TABLE IF NOT EXISTS hcs_raw.cms_medicaid_drug_spending (
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

CREATE TABLE IF NOT EXISTS hcs_raw.cms_dme_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (TEXT per CMS PUF spec)
    npi                         TEXT,
    provider_last_org_name      TEXT,
    provider_first_name         TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_state_fips         TEXT,
    provider_zip5               TEXT,
    provider_ruca               TEXT,
    provider_type               TEXT,
    -- HCPCS / service
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    suplr_rentl_ind             TEXT,
    -- Supplier counts
    tot_suplrs                  INTEGER,
    tot_suplr_benes             INTEGER,
    tot_suplr_clms              INTEGER,
    tot_suplr_srvcs             INTEGER,
    -- Averages (per-claim averages from CMS PUF)
    avg_suplr_sbmtd_chrg        NUMERIC(18,2),
    avg_suplr_mdcr_alowd_amt    NUMERIC(18,2),
    avg_suplr_mdcr_pymt_amt     NUMERIC(18,2),
    avg_suplr_mdcr_stdzd_amt    NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_home_health (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (TEXT per CMS PUF spec)
    provider_id                 TEXT,
    provider_name               TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    -- Home health episode service
    hh_srvc_cd                  TEXT,
    hh_srvc_desc                TEXT,
    -- Utilization metrics
    tot_epsd_stay               INTEGER,
    tot_benes                   INTEGER,
    -- Payment averages
    avg_hh_mdcr_pymt_amt        NUMERIC(18,2),
    avg_hh_outlier_pymt         NUMERIC(18,2),
    -- Demographics
    avg_age                     NUMERIC(5,2),
    female_pct                  NUMERIC(5,2),
    dual_pct                    NUMERIC(5,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospice_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (TEXT per CMS PUF spec)
    provider_id                 TEXT,
    provider_name               TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    -- Hospice service code
    hspce_cd                    TEXT,
    hspce_desc                  TEXT,
    -- Utilization metrics
    tot_benes                   INTEGER,
    -- Payment amounts
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    tot_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    -- Demographics
    avg_age                     NUMERIC(5,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_snf_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (TEXT per CMS PUF spec)
    provider_id                 TEXT,
    provider_name               TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    -- RUG (Resource Utilization Group) code — grain of the PUF
    rug_cd                      TEXT,
    rug_desc                    TEXT,
    -- Utilization metrics
    tot_benes                   INTEGER,
    tot_cvrd_days               INTEGER,
    avg_cvrd_days               NUMERIC(10,2),
    -- Payment amounts
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_alowd_amt          NUMERIC(18,2),
    tot_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_outpatient_puf (
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

CREATE TABLE IF NOT EXISTS hcs_raw.cms_referring_providers (
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

CREATE TABLE IF NOT EXISTS hcs_raw.cms_ordering_providers (
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

CREATE TABLE IF NOT EXISTS hcs_raw.cms_lab_services (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (TEXT per CMS PUF spec)
    npi                         TEXT,
    provider_last_org_name      TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    provider_type               TEXT,
    -- HCPCS / service
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    -- Utilization metrics
    tot_benes                   INTEGER,
    tot_srvcs                   INTEGER,
    -- Payment totals and averages
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_stdzd_amt          NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_imaging_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (TEXT per CMS PUF spec)
    npi                         TEXT,
    provider_last_org_name      TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    provider_type               TEXT,
    -- HCPCS / service
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    -- Utilization metrics
    tot_benes                   INTEGER,
    tot_srvcs                   INTEGER,
    -- Payment totals and averages
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_stdzd_amt          NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_mental_health_puf (
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

CREATE TABLE IF NOT EXISTS hcs_raw.cms_opioid_puf (
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

CREATE TABLE IF NOT EXISTS hcs_raw.cms_telehealth_puf (
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

CREATE TABLE IF NOT EXISTS hcs_raw.cms_geographic_variation (
    id BIGSERIAL PRIMARY KEY,
    bene_geo_lvl TEXT, bene_geo_desc TEXT, bene_geo_cd TEXT,
    bene_age_lvl TEXT, bene_demo_lvl TEXT, bene_demo_desc TEXT,
    bene_mcc_lvl TEXT,
    year INTEGER,
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

CREATE TABLE IF NOT EXISTS hcs_raw.cms_chronic_conditions (
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

CREATE TABLE IF NOT EXISTS hcs_raw.cms_dual_eligible (
    id BIGSERIAL PRIMARY KEY,
    state_cd TEXT, state_name TEXT,
    dual_elgbl_lvl TEXT, dual_elgbl_desc TEXT,
    tot_benes INTEGER, ffs_benes INTEGER, ma_benes INTEGER,
    dual_elgbl_full_benes INTEGER, dual_elgbl_prtl_benes INTEGER,
    non_dual_benes INTEGER, lis_benes INTEGER,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_enrollment_puf (
    id BIGSERIAL PRIMARY KEY,
    state_cd TEXT, county_cd TEXT, county_desc TEXT,
    bene_demo_lvl TEXT, bene_demo_desc TEXT, bene_age_lvl TEXT,
    tot_benes INTEGER, orgnl_mdcr_benes INTEGER,
    ma_benes INTEGER, esrd_benes INTEGER, dsbl_benes INTEGER,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_claim_type_puf (
    id BIGSERIAL PRIMARY KEY,
    bene_geo_lvl TEXT, bene_geo_desc TEXT,
    clm_type TEXT, clm_type_desc TEXT,
    tot_clms BIGINT, tot_benes INTEGER,
    tot_mdcr_pymt_amt NUMERIC(18,2),
    avg_mdcr_pymt_amt NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcs_raw.cms_utilization_puf (
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

CREATE TABLE IF NOT EXISTS hcs_raw.cms_cost_reports_puf (
    id                      BIGSERIAL PRIMARY KEY,
    provider_id             TEXT NOT NULL,
    hospital_name           TEXT,
    city                    TEXT,
    state                   TEXT,
    zip_code                TEXT,
    fiscal_year_begin       DATE,
    fiscal_year_end         DATE,
    total_beds              INTEGER,
    total_discharges        INTEGER,
    net_patient_revenue     NUMERIC(18,2),
    total_operating_expenses NUMERIC(18,2),
    operating_margin        NUMERIC(10,4),
    _source_year            INTEGER NOT NULL,
    _source_hash            TEXT NOT NULL,
    _source_file            TEXT,
    _loaded_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, fiscal_year_begin, _source_year)
);

-- ============================================================================
-- 4. MOL_SILVER NEW TABLES
-- ============================================================================

-- Publication evidence (live table — promoted from staging by SQLMesh T038)
CREATE TABLE IF NOT EXISTS mol_silver.publication_evidence (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_hash        TEXT NOT NULL UNIQUE,  -- md5(pmid || endpoint_name)
    molecule_id         UUID,
    trial_nct_id        TEXT,
    pmid                TEXT NOT NULL,
    doi                 TEXT,
    endpoint_name       TEXT NOT NULL,
    endpoint_type       TEXT,   -- 'primary', 'secondary', 'exploratory'
    hazard_ratio        NUMERIC(10,4),
    p_value             NUMERIC(10,6),
    response_rate       NUMERIC(10,4),
    median_survival_months NUMERIC(10,2),
    sample_size         INTEGER,
    confidence_score    NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review        BOOLEAN NOT NULL DEFAULT FALSE,
    evidence_date       DATE,
    source_model        TEXT NOT NULL DEFAULT 'publication_evidence_extractor',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Staging table — agent writes here; SQLMesh promotes to live (T037, T038)
CREATE TABLE IF NOT EXISTS mol_silver.publication_evidence_staging (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_hash        TEXT NOT NULL UNIQUE,
    molecule_id         UUID,
    trial_nct_id        TEXT,
    pmid                TEXT NOT NULL,
    doi                 TEXT,
    endpoint_name       TEXT NOT NULL,
    endpoint_type       TEXT,
    hazard_ratio        NUMERIC(10,4),
    p_value             NUMERIC(10,6),
    response_rate       NUMERIC(10,4),
    median_survival_months NUMERIC(10,2),
    sample_size         INTEGER,
    confidence_score    NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review        BOOLEAN NOT NULL DEFAULT FALSE,
    evidence_date       DATE,
    source_model        TEXT NOT NULL DEFAULT 'publication_evidence_extractor',
    staged_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    promoted_at         TIMESTAMPTZ
);

-- Physician payments (Open Payments normalized)
CREATE TABLE IF NOT EXISTS mol_silver.physician_payments (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    physician_profile_id            TEXT,
    physician_first_name            TEXT,
    physician_last_name             TEXT,
    physician_specialty             TEXT,
    npi                             TEXT,
    manufacturer_name               TEXT,
    payment_amount                  NUMERIC(18,2),
    payment_date                    DATE,
    nature_of_payment               TEXT,
    recipient_state                 TEXT,
    -- Molecule linkage (may be NULL if not linkable)
    molecule_id                     UUID,
    linked_drug_name                TEXT,
    -- Metadata
    _source_year                    INTEGER NOT NULL,
    _loaded_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Research grants (NIH Reporter normalized)
CREATE TABLE IF NOT EXISTS mol_silver.research_grants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_number      TEXT NOT NULL UNIQUE,
    project_title       TEXT,
    fiscal_year         INTEGER,
    award_amount        NUMERIC(18,2),
    pi_names            JSONB,
    organization_name   TEXT,
    abstract_text       TEXT,
    -- Molecule linkage
    molecule_id         UUID,
    linked_drug_name    TEXT,
    -- Metadata
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Agent quarantine — records with confidence < 0.5 (all agents write here)
CREATE TABLE IF NOT EXISTS mol_silver.agent_quarantine (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name      TEXT NOT NULL,
    record_id       TEXT,
    source_table    TEXT,
    raw_input       JSONB,
    agent_output    JSONB,
    confidence_score NUMERIC(5,4),
    failure_reason  TEXT,
    quarantined_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at     TIMESTAMPTZ,
    reviewer_note   TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_quarantine_agent_name ON mol_silver.agent_quarantine (agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_quarantine_confidence ON mol_silver.agent_quarantine (confidence_score);

-- ============================================================================
-- 5. HCS_SILVER AGENT OUTPUT TABLES (skeleton DDL — agents write here)
-- ============================================================================

CREATE TABLE IF NOT EXISTS hcs_silver.service_lines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npi             TEXT NOT NULL,
    service_line    TEXT NOT NULL,   -- e.g., 'cardiac_surgery', 'interventional_cardiology'
    confidence_score NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review    BOOLEAN NOT NULL DEFAULT FALSE,
    agent_output    JSONB,
    _source_year    INTEGER,
    _loaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, service_line, _source_year)
);

CREATE TABLE IF NOT EXISTS hcs_silver.idn_hierarchy (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_npi           TEXT NOT NULL,
    parent_organization TEXT NOT NULL,
    relationship_type   TEXT,   -- 'owned', 'affiliated', 'contracted'
    confidence_score    NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review        BOOLEAN NOT NULL DEFAULT FALSE,
    agent_output        JSONB,
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (child_npi, parent_organization)
);

CREATE TABLE IF NOT EXISTS hcs_silver.referral_network (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referring_npi   TEXT NOT NULL,
    receiving_npi   TEXT NOT NULL,
    referral_volume INTEGER,
    confidence_score NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review    BOOLEAN NOT NULL DEFAULT FALSE,
    agent_output    JSONB,
    _source_year    INTEGER,
    _loaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (referring_npi, receiving_npi, _source_year)
);

CREATE TABLE IF NOT EXISTS hcs_silver.verified_contacts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npi                 TEXT NOT NULL,
    verified_phone      TEXT,
    verified_email      TEXT,
    verification_status TEXT NOT NULL,  -- 'verified', 'unverified', 'invalid'
    confidence_score    NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review        BOOLEAN NOT NULL DEFAULT FALSE,
    agent_output        JSONB,
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi)
);

CREATE TABLE IF NOT EXISTS hcs_silver.staffing_decomposition (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id     TEXT NOT NULL,
    role_category   TEXT NOT NULL,   -- e.g., 'RN', 'physician', 'allied_health'
    fte_estimate    NUMERIC(10,2),
    confidence_score NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review    BOOLEAN NOT NULL DEFAULT FALSE,
    agent_output    JSONB,
    _source_year    INTEGER,
    _loaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, role_category, _source_year)
);

CREATE TABLE IF NOT EXISTS hcs_silver.equipment_inventory (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npi             TEXT NOT NULL,
    equipment_category TEXT NOT NULL,   -- e.g., 'cath_lab', 'mri', 'ct_scanner'
    hcpcs_evidence  JSONB,
    confidence_score NUMERIC(5,4) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    needs_review    BOOLEAN NOT NULL DEFAULT FALSE,
    agent_output    JSONB,
    _source_year    INTEGER,
    _loaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, equipment_category, _source_year)
);

-- ============================================================================
-- 6. META.DATA_SOURCES ROWS — 30 NEW SOURCES
-- All use ON CONFLICT DO NOTHING for idempotency.
-- source_name values MUST match the SOURCES dict keys in ingestion/main.py exactly.
-- EMA, Cochrane, DrugBank, PubChem, PubMed already have rows from migration 083.
-- ============================================================================

-- 7 core CMS PUF sources
INSERT INTO meta.data_sources (source_name, source_type, description, is_active)
VALUES
    ('cms_part_d_spending',       'cms_bulk_file', 'CMS Medicare Part D Drug Spending by Drug',          TRUE),
    ('cms_part_b_spending',       'cms_bulk_file', 'CMS Medicare Part B Drug Spending by Manufacturer',  TRUE),
    ('cms_open_payments',         'cms_bulk_file', 'CMS Open Payments (Sunshine Act) physician payments', TRUE),
    ('cms_nppes',                 'cms_bulk_file', 'CMS NPPES National Provider Identifier registry',    TRUE),
    ('cms_inpatient_puf',         'cms_bulk_file', 'CMS Inpatient Public Use File (all DRGs)',           TRUE),
    ('cms_physician_puf',         'cms_bulk_file', 'CMS Medicare Physician and Other Practitioners PUF',  TRUE),
    ('cms_hospital_general_info', 'cms_bulk_file', 'CMS Hospital General Information',                   TRUE)
ON CONFLICT (source_name) DO NOTHING;

-- 21 additional CMS PUF sources
INSERT INTO meta.data_sources (source_name, source_type, description, is_active)
VALUES
    ('cms_medicare_advantage',   'cms_bulk_file', 'CMS Medicare Advantage enrollment data',             TRUE),
    ('cms_medicaid_drug_spending','cms_bulk_file', 'CMS Medicaid drug spending by drug and state',       TRUE),
    ('cms_dme_puf',              'cms_bulk_file', 'CMS Durable Medical Equipment PUF',                  TRUE),
    ('cms_home_health',          'cms_bulk_file', 'CMS Home Health Agency compare data',                 TRUE),
    ('cms_hospice_puf',          'cms_bulk_file', 'CMS Hospice provider utilization PUF',               TRUE),
    ('cms_snf_puf',              'cms_bulk_file', 'CMS Skilled Nursing Facility PUF',                   TRUE),
    ('cms_outpatient_puf',       'cms_bulk_file', 'CMS Hospital Outpatient PUF',                        TRUE),
    ('cms_referring_providers',  'cms_bulk_file', 'CMS Medicare referring provider patterns',            TRUE),
    ('cms_ordering_providers',   'cms_bulk_file', 'CMS Medicare ordering/referring/prescribing PUF',     TRUE),
    ('cms_lab_services',         'cms_bulk_file', 'CMS Medicare lab services utilization PUF',           TRUE),
    ('cms_imaging_puf',          'cms_bulk_file', 'CMS Medicare imaging services PUF',                  TRUE),
    ('cms_mental_health_puf',    'cms_bulk_file', 'CMS Medicare mental health services PUF',             TRUE),
    ('cms_opioid_puf',           'cms_bulk_file', 'CMS Medicare opioid prescribing rates by geography',  TRUE),
    ('cms_telehealth_puf',       'cms_bulk_file', 'CMS Medicare telehealth utilization PUF',             TRUE),
    ('cms_geographic_variation', 'cms_bulk_file', 'CMS Medicare geographic variation public use file',   TRUE),
    ('cms_chronic_conditions',   'cms_bulk_file', 'CMS Medicare chronic conditions prevalence data',     TRUE),
    ('cms_dual_eligible',        'cms_bulk_file', 'CMS Medicare-Medicaid dual eligible beneficiaries',   TRUE),
    ('cms_enrollment_puf',       'cms_bulk_file', 'CMS Medicare enrollment by geography and demographics', TRUE),
    ('cms_claim_type_puf',       'cms_bulk_file', 'CMS Medicare claims by type and service category',   TRUE),
    ('cms_utilization_puf',      'cms_bulk_file', 'CMS Medicare utilization by service category',        TRUE),
    ('cms_cost_reports_puf',     'cms_bulk_file', 'CMS Hospital Cost Reports PUF (all providers)',       TRUE)
ON CONFLICT (source_name) DO NOTHING;

-- 2 new API sources
INSERT INTO meta.data_sources (source_name, source_type, description, is_active)
VALUES
    ('europepmc',  'api_incremental', 'EuropePMC publication search API (incremental by update date)', TRUE),
    ('nih_reporter','api_incremental', 'NIH RePORTER research grants API (incremental by start date)', TRUE)
ON CONFLICT (source_name) DO NOTHING;

-- ============================================================================
-- 7. MOL_RAW TABLES FOR NEW API SOURCES (EuropePMC + NIH Reporter)
-- ============================================================================

-- Follows existing mol_raw pattern: request_timestamp, response_status, response_body JSONB
-- Bronze models read from response_body using JSONB operators (->>, ->)
CREATE TABLE IF NOT EXISTS mol_raw.europepmc_raw (
    id                  BIGSERIAL PRIMARY KEY,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uidx_europepmc_raw_pmid
    ON mol_raw.europepmc_raw ((response_body->>'pmid'))
    WHERE response_body->>'pmid' IS NOT NULL;

CREATE TABLE IF NOT EXISTS mol_raw.nih_reporter_raw (
    id                  BIGSERIAL PRIMARY KEY,
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    _loaded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uidx_nih_reporter_raw_project_num
    ON mol_raw.nih_reporter_raw ((response_body->>'project_num'))
    WHERE response_body->>'project_num' IS NOT NULL;

-- ============================================================================
-- 8. GRANTS — HCS_SILVER / HCS_GOLD ACCESS FOR POSTRGEST WEB_ANON
-- ============================================================================
-- PostgREST exposes hcs_silver and hcs_gold directly (per configmap T016).
-- web_anon role needs USAGE + SELECT to serve unauthenticated reads.
-- Pattern matches the existing mol_silver/mol_gold analyst grants.

-- Create web_anon role if not already present (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
        CREATE ROLE web_anon NOLOGIN;
    END IF;
END
$$;

-- hcs_silver: PostgREST read access
GRANT USAGE ON SCHEMA hcs_silver TO web_anon;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_silver TO web_anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA hcs_silver GRANT SELECT ON TABLES TO web_anon;

-- hcs_gold: PostgREST read access
GRANT USAGE ON SCHEMA hcs_gold TO web_anon;
GRANT SELECT ON ALL TABLES IN SCHEMA hcs_gold TO web_anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA hcs_gold GRANT SELECT ON TABLES TO web_anon;

-- analyst role also gets hcs schemas (follows pattern from migration 076)
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        GRANT USAGE ON SCHEMA hcs_silver TO analyst;
        GRANT USAGE ON SCHEMA hcs_gold TO analyst;
        GRANT SELECT ON ALL TABLES IN SCHEMA hcs_silver TO analyst;
        GRANT SELECT ON ALL TABLES IN SCHEMA hcs_gold TO analyst;
    END IF;
END
$$;

COMMIT;
