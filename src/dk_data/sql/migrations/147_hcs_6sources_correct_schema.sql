-- =============================================================================
-- Migration 147: HCS 6-Source Raw Table Schema Correction (idempotent)
-- Feature: 026-fetcher-checkpoint-resume
-- Date: 2026-04-03
-- =============================================================================
-- Context:
--   Migration 075 created 4 of the 6 hcs_raw tables with WRONG schemas
--   (Home Health Compare columns instead of PUF provider×service grain).
--   Migration 094 had the correct schemas and was manually applied to
--   production via `kubectl exec` on 2026-03-27 (never stamped as executed,
--   so it was baselined and bypassed in the normal migration run).
--
--   This migration is the idempotent, auditable record of that manual fix.
--   It detects the wrong schema via sentinel columns that only exist in the
--   migration-075 version and rebuilds each affected table if needed.
--   Tables already on the correct schema (from the manual 094 apply) are
--   left untouched.
--
-- Tables corrected:
--   hcs_raw.cms_home_health   — wrong: cms_certification_number, offers_*
--                               right: provider_id × hh_srvc_cd grain
--   hcs_raw.cms_hospice_puf   — wrong: cms_certification_number, facility_*
--                               right: provider_id × hspce_cd grain
--   hcs_raw.cms_snf_puf       — wrong: cms_certification_number, ownership_type
--                               right: provider_id × rug_cd grain
--   hcs_raw.cms_dme_puf       — wrong: nppes_provider_last_org_name, hcpcs_code
--                               right: npi × hcpcs_cd grain with avg columns
--   hcs_raw.cms_lab_services  — created fresh if missing (no schema in 075)
--   hcs_raw.cms_imaging_puf   — created fresh if missing (no schema in 075)
-- =============================================================================

BEGIN;

-- Ensure schema exists (safe no-op if already present)
CREATE SCHEMA IF NOT EXISTS hcs_raw;

-- ============================================================================
-- 1. cms_home_health
--    Sentinel column for wrong schema: cms_certification_number
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_home_health'
          AND column_name  = 'cms_certification_number'
    ) THEN
        RAISE NOTICE 'cms_home_health: wrong schema detected (migration 075 version), rebuilding...';
        DROP TABLE hcs_raw.cms_home_health CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_home_health (
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
    tot_epsd_stay               INTEGER,        -- episode-level stays
    tot_benes                   INTEGER,        -- unique beneficiaries
    -- Payment averages (dollar amounts)
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
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_id, hh_srvc_cd, _source_year)
);

CREATE INDEX IF NOT EXISTS idx_cms_home_health_provider
    ON hcs_raw.cms_home_health (provider_id, _source_year);
CREATE INDEX IF NOT EXISTS idx_cms_home_health_srvc_cd
    ON hcs_raw.cms_home_health (hh_srvc_cd);

-- ============================================================================
-- 2. cms_hospice_puf
--    Sentinel column for wrong schema: cms_certification_number
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_hospice_puf'
          AND column_name  = 'cms_certification_number'
    ) THEN
        RAISE NOTICE 'cms_hospice_puf: wrong schema detected (migration 075 version), rebuilding...';
        DROP TABLE hcs_raw.cms_hospice_puf CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospice_puf (
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
    tot_benes                   INTEGER,        -- unique beneficiaries
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
-- 3. cms_snf_puf
--    Sentinel column for wrong schema: cms_certification_number
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_snf_puf'
          AND column_name  = 'cms_certification_number'
    ) THEN
        RAISE NOTICE 'cms_snf_puf: wrong schema detected (migration 075 version), rebuilding...';
        DROP TABLE hcs_raw.cms_snf_puf CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_snf_puf (
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
    tot_benes                   INTEGER,        -- unique beneficiaries
    tot_cvrd_days               INTEGER,        -- total covered days
    avg_cvrd_days               NUMERIC(10,2),  -- average covered days per stay
    -- Payment amounts (dollar amounts)
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
-- 4. cms_dme_puf
--    Sentinel column for wrong schema: nppes_provider_last_org_name
--    (correct schema uses provider_last_org_name without nppes_ prefix)
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_dme_puf'
          AND column_name  = 'nppes_provider_last_org_name'
    ) THEN
        RAISE NOTICE 'cms_dme_puf: wrong schema detected (migration 075 version), rebuilding...';
        DROP TABLE hcs_raw.cms_dme_puf CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_dme_puf (
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
    -- Supplier counts (whole counts)
    tot_suplrs                  INTEGER,
    tot_suplr_benes             INTEGER,
    tot_suplr_clms              INTEGER,
    tot_suplr_srvcs             INTEGER,
    -- Per-claim averages (dollar amounts)
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
-- 5. cms_lab_services
--    Not created by migration 075 — CREATE TABLE IF NOT EXISTS is safe on both
--    fresh environments and prod (where 094 already created it correctly).
-- ============================================================================
CREATE TABLE IF NOT EXISTS hcs_raw.cms_lab_services (
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
    tot_benes                   INTEGER,        -- unique beneficiaries
    tot_srvcs                   INTEGER,        -- total services
    -- Payment amounts (dollar amounts)
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
--    Not created by migration 075 — CREATE TABLE IF NOT EXISTS is safe on both
--    fresh environments and prod (where 094 already created it correctly).
-- ============================================================================
CREATE TABLE IF NOT EXISTS hcs_raw.cms_imaging_puf (
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
    tot_benes                   INTEGER,        -- unique beneficiaries
    tot_srvcs                   INTEGER,        -- total services
    -- Payment amounts (dollar amounts)
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
-- 7. Re-grant permissions
--    Safe to re-run: GRANT is idempotent in PostgreSQL.
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
END $$;

COMMIT;
