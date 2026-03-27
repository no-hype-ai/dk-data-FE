-- =============================================================================
-- Rollback for Migration 094: HCS 6-Source Raw Table Schema Fix
-- Feature: 019-cms-puf-platform-reconciliation
-- =============================================================================
-- Migration 094 dropped and recreated 6 tables with correct CMS PUF schemas.
-- This rollback restores the old (wrong) migration 085 versions for emergency
-- recovery only.
--
-- WARNING: Any data loaded under migration 094 will be LOST on rollback.
-- The old schemas had wrong column names and cannot re-receive 094 data.
-- =============================================================================

BEGIN;

-- ============================================================================
-- 1. cms_dme_puf — restore migration 085 wrong version
--    Old schema: supplier_type, total_suppliers, total_unique_benes,
--                total_submitted_chrg_amt, total_medicare_allowed_amt,
--                total_medicare_payment_amt (aggregate totals, wrong grain)
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_dme_puf CASCADE;

CREATE TABLE hcs_raw.cms_dme_puf (
    id                          BIGSERIAL PRIMARY KEY,
    npi                         TEXT,
    supplier_type               TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    suplr_rental_ind            TEXT,
    total_suppliers             INTEGER,
    bene_unique_cnt             INTEGER,
    tot_suplr_clms              INTEGER,
    tot_suplr_srvcs             INTEGER,
    tot_suplr_sbmtd_chrg        NUMERIC(18,2),
    total_submitted_chrg_amt    NUMERIC(18,2),
    total_medicare_allowed_amt  NUMERIC(18,2),
    total_medicare_payment_amt  NUMERIC(18,2),
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 2. cms_home_health — restore migration 085 wrong version
--    Old schema: Home Health Compare columns (not CMS PUF):
--    cms_certification_number, agency_name, street_address, type_of_ownership,
--    offers_nursing_care_services, etc.
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_home_health CASCADE;

CREATE TABLE hcs_raw.cms_home_health (
    id                                  BIGSERIAL PRIMARY KEY,
    provider_id                         TEXT,
    agency_name                         TEXT,
    street_address                      TEXT,
    city                                TEXT,
    state                               TEXT,
    zip_code                            TEXT,
    type_of_ownership                   TEXT,
    offers_nursing_care_services        BOOLEAN,
    offers_physical_therapy             BOOLEAN,
    offers_occupational_therapy         BOOLEAN,
    offers_speech_pathology             BOOLEAN,
    offers_medical_social_services      BOOLEAN,
    offers_home_health_aide_services    BOOLEAN,
    quality_of_patient_care_star_rating NUMERIC(3,1),
    tot_epis                            INTEGER,
    tot_hha_mdcr_pymt_amt               NUMERIC(18,2),
    avg_hha_mdcr_pymt_amt               NUMERIC(18,2),
    _source_year                        INTEGER NOT NULL,
    _source_hash                        TEXT NOT NULL,
    _source_file                        TEXT,
    _loaded_at                          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, _source_year)
);

-- ============================================================================
-- 3. cms_hospice_puf — restore migration 085 wrong version
--    Old schema: npi (not provider_id/CCN), organization_name,
--                total_medicare_beneficiaries, average_length_of_service,
--                total_charges
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_hospice_puf CASCADE;

CREATE TABLE hcs_raw.cms_hospice_puf (
    id                              BIGSERIAL PRIMARY KEY,
    npi                             TEXT,
    organization_name               TEXT,
    city                            TEXT,
    state                           TEXT,
    zip_code                        TEXT,
    total_medicare_beneficiaries    INTEGER,
    total_charges                   NUMERIC(18,2),
    total_medicare_payment          NUMERIC(18,2),
    average_length_of_service       NUMERIC(10,2),
    avg_mdcr_pymt_per_bene          NUMERIC(18,2),
    _source_year                    INTEGER NOT NULL,
    _source_hash                    TEXT NOT NULL,
    _source_file                    TEXT,
    _loaded_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, _source_year)
);

-- ============================================================================
-- 4. cms_snf_puf — restore migration 085 wrong version
--    Old schema: snf_type, ownership_type, total_episodes,
--                total_medicare_payment, average_payment_per_episode
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_snf_puf CASCADE;

CREATE TABLE hcs_raw.cms_snf_puf (
    id                          BIGSERIAL PRIMARY KEY,
    provider_id                 TEXT,
    facility_name               TEXT,
    city                        TEXT,
    state                       TEXT,
    zip_code                    TEXT,
    snf_type                    TEXT,
    ownership_type              TEXT,
    total_episodes              INTEGER,
    total_medicare_payment      NUMERIC(18,2),
    average_payment_per_episode NUMERIC(18,2),
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, _source_year)
);

-- ============================================================================
-- 5. cms_lab_services — restore migration 085 wrong version
--    Old schema: aggregate by HCPCS only (no NPI), with old total columns
--                and non-existent modality column
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_lab_services CASCADE;

CREATE TABLE hcs_raw.cms_lab_services (
    id                          BIGSERIAL PRIMARY KEY,
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    total_labs                  INTEGER,
    total_unique_benes          INTEGER,
    total_services              BIGINT,
    average_medicare_allowed_amt    NUMERIC(18,2),
    average_medicare_payment_amt    NUMERIC(18,2),
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (hcpcs_cd, _source_year)
);

-- ============================================================================
-- 6. cms_imaging_puf — restore migration 085 wrong version
--    Old schema: aggregate with non-existent modality column
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_imaging_puf CASCADE;

CREATE TABLE hcs_raw.cms_imaging_puf (
    id                          BIGSERIAL PRIMARY KEY,
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    modality                    TEXT,
    total_unique_benes          INTEGER,
    total_services              BIGINT,
    average_medicare_allowed_amt    NUMERIC(18,2),
    average_medicare_payment_amt    NUMERIC(18,2),
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (hcpcs_cd, modality, _source_year)
);

COMMIT;
