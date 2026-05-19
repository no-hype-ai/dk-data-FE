-- =============================================================================
-- Migration 147: HCS 6-Source Raw Table Schema Reconciliation (idempotent)
-- Feature: 026-fetcher-checkpoint-resume
-- Date: 2026-04-03
-- =============================================================================
-- Context:
--   Migration 075 (PR #205) created 4 of the 6 hcs_raw tables with WRONG
--   schemas — Home Health Compare columns instead of the CMS PUF
--   provider×service grain that the SQLMesh bronze models expect.
--
--   Migration 094 had the correct provider×service schemas and was manually
--   applied to production via `kubectl exec` on 2026-03-27. It was baselined
--   (stamped but never executed by the migration runner) so it was silently
--   skipped in all subsequent deployments.
--
--   This migration is the idempotent, auditable record of that manual fix.
--
-- Strategy per table:
--   - If a sentinel column from migration 075 is present → DROP + RECREATE
--   - If the table already has the correct 094 schema → CREATE IF NOT EXISTS
--     is a no-op, existing rows are preserved
--   - If the table does not exist (fresh environment) → CREATE
--
-- Metadata column convention (_source_* prefix):
--   All 6 tables use underscore-prefixed metadata columns consistent with
--   the convention adopted in migration 094 and the SQLMesh bronze models:
--     _source_year  INT            — calendar year of the source file
--     _source_hash  TEXT           — MD5 of the source file (dedup sentinel)
--     _source_file  TEXT           — filename for traceability
--     _loaded_at    TIMESTAMPTZ    — row insertion timestamp (DEFAULT NOW())
--
-- Sentinels for wrong schema:
--   cms_certification_number  → migration 075 (cms_home_health, cms_hospice_puf, cms_snf_puf)
--   nppes_provider_last_org_name → migration 075 (cms_dme_puf)
-- =============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS hcs_raw;

-- ============================================================================
-- 1. cms_home_health
--    Migration 075 sentinel: cms_certification_number
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_home_health'
          AND column_name  = 'cms_certification_number'
    ) THEN
        RAISE NOTICE 'cms_home_health: migration-075 schema detected, rebuilding with correct PUF schema';
        DROP TABLE hcs_raw.cms_home_health CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_home_health (
    id                          BIGSERIAL PRIMARY KEY,
    provider_id                 TEXT,
    provider_name               TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    hh_srvc_cd                  TEXT,
    hh_srvc_desc                TEXT,
    tot_epsd_stay               INTEGER,
    tot_benes                   INTEGER,
    avg_hh_mdcr_pymt_amt        NUMERIC(18,2),
    avg_hh_outlier_pymt         NUMERIC(18,2),
    avg_age                     NUMERIC(5,2),
    female_pct                  NUMERIC(5,2),
    dual_pct                    NUMERIC(5,2),
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
--    Migration 075 sentinel: cms_certification_number
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_hospice_puf'
          AND column_name  = 'cms_certification_number'
    ) THEN
        RAISE NOTICE 'cms_hospice_puf: migration-075 schema detected, rebuilding with correct PUF schema';
        DROP TABLE hcs_raw.cms_hospice_puf CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_hospice_puf (
    id                          BIGSERIAL PRIMARY KEY,
    provider_id                 TEXT,
    provider_name               TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    hspce_cd                    TEXT,
    hspce_desc                  TEXT,
    tot_benes                   INTEGER,
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    tot_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    avg_age                     NUMERIC(5,2),
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
--    Migration 075 sentinel: cms_certification_number
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_snf_puf'
          AND column_name  = 'cms_certification_number'
    ) THEN
        RAISE NOTICE 'cms_snf_puf: migration-075 schema detected, rebuilding with correct PUF schema';
        DROP TABLE hcs_raw.cms_snf_puf CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_snf_puf (
    id                          BIGSERIAL PRIMARY KEY,
    provider_id                 TEXT,
    provider_name               TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    rug_cd                      TEXT,
    rug_desc                    TEXT,
    tot_benes                   INTEGER,
    tot_cvrd_days               INTEGER,
    avg_cvrd_days               NUMERIC(10,2),
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_alowd_amt          NUMERIC(18,2),
    tot_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
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
--    Migration 075 sentinel: nppes_provider_last_org_name
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_dme_puf'
          AND column_name  = 'nppes_provider_last_org_name'
    ) THEN
        RAISE NOTICE 'cms_dme_puf: migration-075 schema detected, rebuilding with correct PUF schema';
        DROP TABLE hcs_raw.cms_dme_puf CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS hcs_raw.cms_dme_puf (
    id                          BIGSERIAL PRIMARY KEY,
    npi                         TEXT,
    provider_last_org_name      TEXT,
    provider_first_name         TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_state_fips         TEXT,
    provider_zip5               TEXT,
    provider_ruca               TEXT,
    provider_type               TEXT,
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    suplr_rentl_ind             TEXT,
    tot_suplrs                  INTEGER,
    tot_suplr_benes             INTEGER,
    tot_suplr_clms              INTEGER,
    tot_suplr_srvcs             INTEGER,
    avg_suplr_sbmtd_chrg        NUMERIC(18,2),
    avg_suplr_mdcr_alowd_amt    NUMERIC(18,2),
    avg_suplr_mdcr_pymt_amt     NUMERIC(18,2),
    avg_suplr_mdcr_stdzd_amt    NUMERIC(18,2),
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
--    Not created by migration 075. CREATE IF NOT EXISTS is safe on all envs.
-- ============================================================================
CREATE TABLE IF NOT EXISTS hcs_raw.cms_lab_services (
    id                          BIGSERIAL PRIMARY KEY,
    npi                         TEXT,
    provider_last_org_name      TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    provider_type               TEXT,
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    tot_benes                   INTEGER,
    tot_srvcs                   INTEGER,
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_stdzd_amt          NUMERIC(18,2),
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
--    Not created by migration 075. CREATE IF NOT EXISTS is safe on all envs.
-- ============================================================================
CREATE TABLE IF NOT EXISTS hcs_raw.cms_imaging_puf (
    id                          BIGSERIAL PRIMARY KEY,
    npi                         TEXT,
    provider_last_org_name      TEXT,
    provider_city               TEXT,
    provider_state              TEXT,
    provider_zip5               TEXT,
    provider_type               TEXT,
    hcpcs_cd                    TEXT,
    hcpcs_desc                  TEXT,
    tot_benes                   INTEGER,
    tot_srvcs                   INTEGER,
    tot_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_alowd_amt          NUMERIC(18,2),
    avg_mdcr_pymt_amt           NUMERIC(18,2),
    avg_mdcr_stdzd_amt          NUMERIC(18,2),
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
-- 7. Grants (idempotent)
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
