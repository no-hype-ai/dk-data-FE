-- ⚠️ DEPLOYMENT WARNING: This migration drops and recreates tables from migration 086.
-- These must be applied in the same deployment batch as 086 — do NOT run 086 with
-- data ingestion enabled before applying this migration, or data will be lost.
-- See: PR #149 FINDINGS.md items #1 and #5

-- =============================================================================
-- Migration 094: HCS 6-Source Raw Table Schema Fix
-- Feature: 019-cms-puf-platform-reconciliation
-- Date: 2026-03-27
-- =============================================================================
-- Rebuilds 6 hcs_raw tables whose migration 085 DDL used generic/wrong column
-- names that do not match either the CMS raw PUF field names or what the
-- Python loaders write.
--
-- Sources fixed:
--   1. cms_dme_puf        — was: supplier_type, total_suppliers, total_unique_benes,
--                                 total_submitted_chrg_amt, total_medicare_allowed_amt,
--                                 total_medicare_payment_amt (all aggregate totals, wrong grain)
--                           now: exact CMS PUF avg-per-claim columns with provider location
--   2. cms_home_health    — was: cms_certification_number, type_of_ownership,
--                                 offers_nursing_care_services, etc. (Home Health Compare, not PUF)
--                           now: Rndrng_Prvdr_Id / HH_Srvc_Cd grain with correct PUF columns
--   3. cms_hospice_puf    — was: npi, organization_name, total_medicare_beneficiaries,
--                                 average_length_of_service, total_charges (all wrong)
--                           now: provider_id / HSPCE_CD grain with correct PUF columns
--   4. cms_snf_puf        — was: snf_type, ownership_type, total_episodes,
--                                 total_medicare_payment, average_payment_per_episode (all wrong)
--                           now: provider_id / RUG_CD grain with correct PUF columns
--   5. cms_lab_services   — was: aggregate by HCPCS only (missing provider/NPI)
--                           now: provider-level NPI x HCPCS grain with avg columns
--   6. cms_imaging_puf    — was: aggregate with non-existent modality column (missing provider)
--                           now: provider-level NPI x HCPCS grain with avg columns
--
-- Strategy: DROP + RECREATE each table.
-- ROLLBACK: see 094_rollback.sql
-- Run: doppler run -- python -m dk_data.scripts.run_migration src/dk_data/sql/migrations/094_hcs_6sources_raw_schema_fix.sql
-- =============================================================================

BEGIN;

-- ============================================================================
-- 1. cms_dme_puf
--    CMS raw fields: Rndrng_NPI, Rndrng_Prvdr_Last_Org_Name, Rndrng_Prvdr_First_Name,
--    Rndrng_Prvdr_City, Rndrng_Prvdr_State_Abrvtn, Rndrng_Prvdr_State_FIPS,
--    Rndrng_Prvdr_Zip5, Rndrng_Prvdr_RUCA, Rndrng_Prvdr_Type, HCPCS_Cd, HCPCS_Desc,
--    Suplr_Rentl_Ind, Tot_Suplrs, Tot_Suplr_Benes, Tot_Suplr_Clms, Tot_Suplr_Srvcs,
--    Avg_Suplr_Sbmtd_Chrg, Avg_Suplr_Mdcr_Alowd_Amt, Avg_Suplr_Mdcr_Pymt_Amt,
--    Avg_Suplr_Mdcr_Stdzd_Amt
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_dme_puf CASCADE;

CREATE TABLE hcs_raw.cms_dme_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (NPI as TEXT — 10-digit numeric string)
    npi                         TEXT,
    provider_last_org_name      TEXT,
    provider_first_name         TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_state_fips         TEXT,           -- FIPS code as TEXT (leading zeros)
    provider_zip5               TEXT,           -- ZIP as TEXT (leading zeros)
    provider_ruca               TEXT,
    provider_type               TEXT,
    -- HCPCS / service
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    suplr_rentl_ind             TEXT,           -- Y/N rental indicator
    -- Supplier counts (INTEGER — whole counts)
    tot_suplrs                  INTEGER,
    tot_suplr_benes             INTEGER,
    tot_suplr_clms              INTEGER,
    tot_suplr_srvcs             INTEGER,
    -- Per-claim averages (NUMERIC — dollar amounts)
    avg_suplr_sbmtd_chrg        NUMERIC(18,2),
    avg_suplr_mdcr_alowd_amt    NUMERIC(18,2),
    avg_suplr_mdcr_pymt_amt     NUMERIC(18,2),
    avg_suplr_mdcr_stdzd_amt    NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, hcpcs_cd, provider_type, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_dme_puf_npi
    ON hcs_raw.cms_dme_puf (npi, _source_year);
CREATE INDEX IF NOT EXISTS idx_cms_dme_puf_hcpcs
    ON hcs_raw.cms_dme_puf (hcpcs_cd);

-- ============================================================================
-- 2. cms_home_health
--    CMS raw fields: Rndrng_Prvdr_Id, Rndrng_Prvdr_Name, Rndrng_Prvdr_City,
--    Rndrng_Prvdr_State_Abrvtn, Rndrng_Prvdr_Zip5, HH_Srvc_Cd, HH_Srvc_Desc,
--    Tot_Epsd_Stay, Tot_Benes, Avg_HH_Mdcr_Pymt_Amt, Avg_HH_Outlier_Pymt,
--    Avg_Age, Female_Pct, Dual_Pct
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_home_health CASCADE;

CREATE TABLE hcs_raw.cms_home_health (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (CCN as TEXT — 6-character, may have leading zeros)
    provider_id                 TEXT,
    provider_name               TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,           -- ZIP as TEXT (leading zeros)
    -- Home health episode service code
    hh_srvc_cd                  TEXT,
    hh_srvc_desc                TEXT,
    -- Utilization metrics
    tot_epsd_stay               INTEGER,        -- episode-level stays (INTEGER)
    tot_benes                   INTEGER,        -- unique beneficiaries (INTEGER)
    -- Payment averages (NUMERIC — dollar amounts)
    avg_hh_mdcr_pymt_amt        NUMERIC(18,2),
    avg_hh_outlier_pymt         NUMERIC(18,2),
    -- Demographics (NUMERIC — rates/ages)
    avg_age                     NUMERIC(5,2),
    female_pct                  NUMERIC(5,2),
    dual_pct                    NUMERIC(5,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, hh_srvc_cd, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_home_health_provider
    ON hcs_raw.cms_home_health (provider_id, _source_year);
CREATE INDEX IF NOT EXISTS idx_cms_home_health_srvc_cd
    ON hcs_raw.cms_home_health (hh_srvc_cd);

-- ============================================================================
-- 3. cms_hospice_puf
--    CMS raw fields: Rndrng_Prvdr_Id, Rndrng_Prvdr_Name, Rndrng_Prvdr_City,
--    Rndrng_Prvdr_State_Abrvtn, Rndrng_Prvdr_Zip5, HSPCE_CD, HSPCE_DESC,
--    Tot_Benes, Tot_Mdcr_Alowd_Amt, Tot_Mdcr_Pymt_Amt, Avg_Mdcr_Pymt_Amt, Avg_Age
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_hospice_puf CASCADE;

CREATE TABLE hcs_raw.cms_hospice_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (CCN as TEXT — 6-character, may have leading zeros)
    provider_id                 TEXT,
    provider_name               TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,           -- ZIP as TEXT (leading zeros)
    -- Hospice service code (type of care)
    hspce_cd                    TEXT,
    hspce_desc                  TEXT,
    -- Utilization and payment metrics
    tot_benes                   INTEGER,        -- unique beneficiaries (INTEGER)
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    tot_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    -- Demographics
    avg_age                     NUMERIC(5,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, hspce_cd, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_hospice_puf_provider
    ON hcs_raw.cms_hospice_puf (provider_id, _source_year);
CREATE INDEX IF NOT EXISTS idx_cms_hospice_puf_hspce_cd
    ON hcs_raw.cms_hospice_puf (hspce_cd);

-- ============================================================================
-- 4. cms_snf_puf
--    CMS raw fields: Rndrng_Prvdr_Id, Rndrng_Prvdr_Name, Rndrng_Prvdr_City,
--    Rndrng_Prvdr_State_Abrvtn, Rndrng_Prvdr_Zip5, RUG_CD, RUG_DESC,
--    Tot_Benes, Tot_Cvrd_Days, Avg_Cvrd_Days, Tot_Mdcr_Alowd_Amt,
--    Avg_Mdcr_Alowd_Amt, Tot_Mdcr_Pymt_Amt, Avg_Mdcr_Pymt_Amt
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_snf_puf CASCADE;

CREATE TABLE hcs_raw.cms_snf_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (CCN as TEXT — 6-character, may have leading zeros)
    provider_id                 TEXT,
    provider_name               TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,           -- ZIP as TEXT (leading zeros)
    -- RUG (Resource Utilization Group) code — defines level of care
    rug_cd                      TEXT,
    rug_desc                    TEXT,
    -- Utilization metrics
    tot_benes                   INTEGER,        -- unique beneficiaries (INTEGER)
    tot_cvrd_days               INTEGER,        -- total covered days (INTEGER)
    avg_cvrd_days               NUMERIC(10,2),  -- average covered days per stay
    -- Payment amounts (NUMERIC — dollar amounts)
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_alowd_amt          NUMERIC(18,2),
    tot_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, rug_cd, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_snf_puf_provider
    ON hcs_raw.cms_snf_puf (provider_id, _source_year);
CREATE INDEX IF NOT EXISTS idx_cms_snf_puf_rug_cd
    ON hcs_raw.cms_snf_puf (rug_cd);

-- ============================================================================
-- 5. cms_lab_services
--    CMS raw fields: Rndrng_NPI, Rndrng_Prvdr_Last_Org_Name, Rndrng_Prvdr_City,
--    Rndrng_Prvdr_State_Abrvtn, Rndrng_Prvdr_Zip5, Rndrng_Prvdr_Type,
--    HCPCS_Cd, HCPCS_Desc, Tot_Benes, Tot_Srvcs, Tot_Mdcr_Alowd_Amt,
--    Avg_Mdcr_Alowd_Amt, Avg_Mdcr_Pymt_Amt, Avg_Mdcr_Stdzd_Amt
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_lab_services CASCADE;

CREATE TABLE hcs_raw.cms_lab_services (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (NPI as TEXT — 10-digit numeric string)
    npi                         TEXT,
    provider_last_org_name      TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,           -- ZIP as TEXT (leading zeros)
    provider_type               TEXT,
    -- HCPCS / service
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    -- Utilization metrics
    tot_benes                   INTEGER,        -- unique beneficiaries (INTEGER)
    tot_srvcs                   INTEGER,        -- total services (INTEGER)
    -- Payment amounts (NUMERIC — dollar amounts)
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_stdzd_amt          NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, hcpcs_cd, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_lab_services_npi
    ON hcs_raw.cms_lab_services (npi, _source_year);
CREATE INDEX IF NOT EXISTS idx_cms_lab_services_hcpcs
    ON hcs_raw.cms_lab_services (hcpcs_cd);

-- ============================================================================
-- 6. cms_imaging_puf
--    CMS raw fields: Rndrng_NPI, Rndrng_Prvdr_Last_Org_Name, Rndrng_Prvdr_City,
--    Rndrng_Prvdr_State_Abrvtn, Rndrng_Prvdr_Zip5, Rndrng_Prvdr_Type,
--    HCPCS_Cd, HCPCS_Desc, Tot_Benes, Tot_Srvcs, Tot_Mdcr_Alowd_Amt,
--    Avg_Mdcr_Alowd_Amt, Avg_Mdcr_Pymt_Amt, Avg_Mdcr_Stdzd_Amt
--    Note: No 'modality' column in CMS Imaging PUF source data.
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_imaging_puf CASCADE;

CREATE TABLE hcs_raw.cms_imaging_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (NPI as TEXT — 10-digit numeric string)
    npi                         TEXT,
    provider_last_org_name      TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,           -- ZIP as TEXT (leading zeros)
    provider_type               TEXT,
    -- HCPCS / service
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    -- Utilization metrics
    tot_benes                   INTEGER,        -- unique beneficiaries (INTEGER)
    tot_srvcs                   INTEGER,        -- total services (INTEGER)
    -- Payment amounts (NUMERIC — dollar amounts)
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_stdzd_amt          NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (npi, hcpcs_cd, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_imaging_puf_npi
    ON hcs_raw.cms_imaging_puf (npi, _source_year);
CREATE INDEX IF NOT EXISTS idx_cms_imaging_puf_hcpcs
    ON hcs_raw.cms_imaging_puf (hcpcs_cd);

-- ============================================================================
-- 7. Re-grant web_anon and analyst access (tables were dropped + recreated)
-- ============================================================================

GRANT SELECT ON hcs_raw.cms_dme_puf       TO web_anon;
GRANT SELECT ON hcs_raw.cms_home_health    TO web_anon;
GRANT SELECT ON hcs_raw.cms_hospice_puf    TO web_anon;
GRANT SELECT ON hcs_raw.cms_snf_puf        TO web_anon;
GRANT SELECT ON hcs_raw.cms_lab_services   TO web_anon;
GRANT SELECT ON hcs_raw.cms_imaging_puf    TO web_anon;

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        GRANT SELECT ON hcs_raw.cms_dme_puf       TO analyst;
        GRANT SELECT ON hcs_raw.cms_home_health    TO analyst;
        GRANT SELECT ON hcs_raw.cms_hospice_puf    TO analyst;
        GRANT SELECT ON hcs_raw.cms_snf_puf        TO analyst;
        GRANT SELECT ON hcs_raw.cms_lab_services   TO analyst;
        GRANT SELECT ON hcs_raw.cms_imaging_puf    TO analyst;
    END IF;
END
$$;

COMMIT;
