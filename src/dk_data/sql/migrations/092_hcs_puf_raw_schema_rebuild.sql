-- ⚠️ DEPLOYMENT WARNING: This migration drops and recreates tables from migration 086.
-- These must be applied in the same deployment batch as 086 — do NOT run 086 with
-- data ingestion enabled before applying this migration, or data will be lost.
-- See: PR #149 FINDINGS.md items #1 and #5

-- Migration 092: HCS PUF Raw Table Schema Rebuild
-- Feature: 019-cms-puf-platform-reconciliation
-- Date: 2026-03-27
--
-- Fixes column-name and type drift across 4 raw tables introduced in migration 085:
--   cms_mental_health_puf  — renamed/missing columns, wrong names
--   cms_opioid_puf         — geographic schema replaced by prescriber-drug schema
--   cms_telehealth_puf     — missing HCPCS, provider detail, and average columns
--   cms_medicare_advantage — missing enrollment metrics columns
--
-- Strategy: DROP + RECREATE using IF NOT EXISTS guards where possible, or
-- RENAME/ADD COLUMN for non-breaking cases. Geographic opioid table is replaced
-- wholesale because column semantics changed entirely.
--
-- ROLLBACK: see 092_rollback.sql
--
-- Run: doppler run -- python -m dk_data.scripts.run_migration src/dk_data/sql/migrations/092_hcs_puf_raw_schema_rebuild.sql

BEGIN;

-- ============================================================================
-- 1. cms_mental_health_puf
--    Old schema had: npi, provider_type, provider_name, provider_city,
--                    provider_state, hcpcs_cd, hcpcs_desc,
--                    total_benes, total_services, total_medicare_payment_amt
--    New schema:     npi, provider_last_org_name, provider_first_name,
--                    provider_city, provider_state, provider_zip5, provider_type,
--                    hcpcs_cd, hcpcs_desc, mh_srvc_ind (BOOLEAN),
--                    tot_benes, tot_srvcs, tot_mdcr_alowd_amt,
--                    avg_mdcr_alowd_amt, avg_mdcr_pymt_amt, avg_mdcr_stdzd_amt
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_mental_health_puf CASCADE;

CREATE TABLE hcs_raw.cms_mental_health_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (NPI as TEXT — NPI is a 10-digit numeric string)
    npi                         TEXT NOT NULL,
    provider_last_org_name      TEXT,
    provider_first_name         TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    provider_type               TEXT,
    -- Service identifiers
    hcpcs_cd                    TEXT NOT NULL,
    hcpcs_desc                  TEXT,
    -- Mental health service indicator (Y/N → BOOLEAN)
    mh_srvc_ind                 BOOLEAN,
    -- Volume metrics
    tot_benes                   INTEGER,
    tot_srvcs                   NUMERIC(18,2),
    -- Payment metrics
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_stdzd_amt          NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (_source_hash, npi, hcpcs_cd, _source_year)
);

CREATE INDEX idx_cms_mental_health_puf_npi
    ON hcs_raw.cms_mental_health_puf (npi);
CREATE INDEX idx_cms_mental_health_puf_hcpcs
    ON hcs_raw.cms_mental_health_puf (hcpcs_cd);
CREATE INDEX idx_cms_mental_health_puf_year
    ON hcs_raw.cms_mental_health_puf (_source_year);

-- ============================================================================
-- 2. cms_opioid_puf
--    Old schema was geographic (state/county/fips/rate) — WRONG.
--    Correct schema is prescriber-drug level (NPI × drug × year).
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_opioid_puf CASCADE;

CREATE TABLE hcs_raw.cms_opioid_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Prescriber identifiers (NPI as TEXT)
    prscrbr_npi                 TEXT NOT NULL,
    prscrbr_last_org_name       TEXT,
    prscrbr_first_name          TEXT,
    prscrbr_city                TEXT,
    prscrbr_state_abrvtn        TEXT,
    prscrbr_state_fips          TEXT,
    prscrbr_type                TEXT,
    prscrbr_type_src            TEXT,
    -- Drug identifiers
    brnd_name                   TEXT,
    gnrc_name                   TEXT,
    -- Drug flags (Y/N → BOOLEAN)
    opioid_drug_flag            BOOLEAN,
    la_opioid_drug_flag         BOOLEAN,
    -- Claim/fill metrics
    tot_clms                    INTEGER,
    tot_30day_fills             NUMERIC(18,2),
    tot_day_suply               INTEGER,
    tot_drug_cst                NUMERIC(18,2),
    tot_benes                   INTEGER,
    -- Opioid-specific metrics (suppressed < 11 → NULL)
    opioid_clms                 INTEGER,
    opioid_benes                INTEGER,
    la_opioid_clms              INTEGER,
    la_opioid_benes             INTEGER,
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (_source_hash, prscrbr_npi, gnrc_name, _source_year)
);

CREATE INDEX idx_cms_opioid_puf_npi
    ON hcs_raw.cms_opioid_puf (prscrbr_npi);
CREATE INDEX idx_cms_opioid_puf_drug
    ON hcs_raw.cms_opioid_puf (gnrc_name);
CREATE INDEX idx_cms_opioid_puf_year
    ON hcs_raw.cms_opioid_puf (_source_year);

-- ============================================================================
-- 3. cms_telehealth_puf
--    Old schema had: npi, provider_type, telehealth_services,
--                    total_unique_benes, total_telehealth_payment
--    New schema adds full provider detail and HCPCS-level granularity.
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_telehealth_puf CASCADE;

CREATE TABLE hcs_raw.cms_telehealth_puf (
    id                          BIGSERIAL PRIMARY KEY,
    -- Provider identifiers (NPI as TEXT)
    npi                         TEXT NOT NULL,
    provider_last_org_name      TEXT,
    provider_first_name         TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    provider_type               TEXT,
    -- Service identifiers
    hcpcs_cd                    TEXT NOT NULL,
    hcpcs_desc                  TEXT,
    -- Telehealth service indicator (Y/N → BOOLEAN)
    th_srvc_ind                 BOOLEAN,
    -- Volume metrics
    tot_benes                   INTEGER,
    tot_srvcs                   NUMERIC(18,2),
    -- Payment metrics
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_stdzd_amt          NUMERIC(18,2),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (_source_hash, npi, hcpcs_cd, _source_year)
);

CREATE INDEX idx_cms_telehealth_puf_npi
    ON hcs_raw.cms_telehealth_puf (npi);
CREATE INDEX idx_cms_telehealth_puf_hcpcs
    ON hcs_raw.cms_telehealth_puf (hcpcs_cd);
CREATE INDEX idx_cms_telehealth_puf_year
    ON hcs_raw.cms_telehealth_puf (_source_year);

-- ============================================================================
-- 4. cms_medicare_advantage
--    Old schema: contract_id, plan_id, segment_id, organization_name,
--                plan_name, plan_type, state, county, fips_county_code,
--                enrolled
--    New schema: adds organization_type, enrollment_data_period, state_fips,
--                county_fips, fips_cd, avg_age, pct_female, avg_risk_score,
--                ma_participation_rate, star_rating.
--    Renames: county → county_fips, fips_county_code → fips_cd,
--             enrolled → enrollment.
-- ============================================================================

DROP TABLE IF EXISTS hcs_raw.cms_medicare_advantage CASCADE;

CREATE TABLE hcs_raw.cms_medicare_advantage (
    id                          BIGSERIAL PRIMARY KEY,
    -- Contract/plan identifiers (TEXT — contract IDs like 'H1234')
    contract_id                 TEXT NOT NULL,
    organization_name           TEXT,
    organization_type           TEXT,
    plan_id                     TEXT NOT NULL,
    plan_name                   TEXT,
    segment_id                  TEXT,
    -- Enrollment period (YYYY-MM)
    enrollment_data_period      TEXT,
    -- Geography (all as TEXT — FIPS codes include leading zeros)
    fips_cd                     TEXT NOT NULL,      -- full 5-digit FIPS
    state_fips                  TEXT,               -- 2-digit state FIPS
    county_fips                 TEXT,               -- 3-digit county FIPS
    -- Enrollment (suppressed values < 11 stored as NULL)
    enrollment                  INTEGER,
    -- Plan quality metrics
    avg_age                     NUMERIC(5,2),
    pct_female                  NUMERIC(5,2),
    avg_risk_score              NUMERIC(8,4),
    ma_participation_rate       NUMERIC(5,2),
    star_rating                 NUMERIC(3,1),
    -- Metadata
    _source_year                INTEGER NOT NULL,
    _source_hash                TEXT NOT NULL,
    _source_file                TEXT,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (_source_hash, contract_id, plan_id, fips_cd, _source_year)
);

CREATE INDEX idx_cms_medicare_advantage_contract
    ON hcs_raw.cms_medicare_advantage (contract_id);
CREATE INDEX idx_cms_medicare_advantage_fips
    ON hcs_raw.cms_medicare_advantage (fips_cd);
CREATE INDEX idx_cms_medicare_advantage_year
    ON hcs_raw.cms_medicare_advantage (_source_year);

-- ============================================================================
-- 5. Re-grant web_anon and analyst access (tables were dropped + recreated)
-- ============================================================================

GRANT SELECT ON hcs_raw.cms_mental_health_puf TO web_anon;
GRANT SELECT ON hcs_raw.cms_opioid_puf        TO web_anon;
GRANT SELECT ON hcs_raw.cms_telehealth_puf     TO web_anon;
GRANT SELECT ON hcs_raw.cms_medicare_advantage TO web_anon;

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        GRANT SELECT ON hcs_raw.cms_mental_health_puf TO analyst;
        GRANT SELECT ON hcs_raw.cms_opioid_puf        TO analyst;
        GRANT SELECT ON hcs_raw.cms_telehealth_puf     TO analyst;
        GRANT SELECT ON hcs_raw.cms_medicare_advantage TO analyst;
    END IF;
END
$$;

COMMIT;
