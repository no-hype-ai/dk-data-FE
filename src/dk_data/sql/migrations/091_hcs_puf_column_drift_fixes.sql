-- =============================================================================
-- Migration 091: HCS Raw Table Column Drift Fixes
-- Feature: 019-cms-puf-platform-reconciliation
-- Date: 2026-03-27
-- =============================================================================
-- Fixes column name drift in hcs_raw tables where migration 085 used either
-- NPPES-internal names or old-format names that don't match what the Python
-- loaders write. Also adds missing columns for newer CMS file formats.
--
-- Changes:
-- 1. hcs_raw.cms_physician_puf
--    - The migration 085 DDL used NPPES-specific internal names
--      (nppes_provider_last_org_name, etc.) while the loader now writes to those
--      exact names. The table was ALREADY using the correct names — no renames
--      needed. ADD missing columns: nppes_provider_street1, nppes_provider_street2,
--      nppes_provider_state_fips, nppes_provider_ruca, nppes_provider_country,
--      total_submitted_chrg_amt (existed as total_submitted_chrg_amt already —
--      verify and add if missing).
--
-- 2. hcs_raw.cms_nppes
--    - Add missing columns: provider_middle_name, provider_name_prefix_text,
--      provider_name_suffix_text, provider_first_line_business_mailing_address,
--      provider_second_line_business_mailing_address,
--      provider_business_mailing_address_country_code,
--      provider_business_mailing_address_fax_number,
--      provider_business_mailing_address_telephone_number.
--    - (Practice-location columns were already added in migration 086.)
--
-- 3. hcs_raw.cms_inpatient_puf
--    - Add missing columns: drg_cd (raw code before description join),
--      provider_state_fips, provider_ruca.
--
-- 4. hcs_raw.cms_outpatient_puf
--    - Add missing columns: provider_name, provider_city, provider_street_address,
--      provider_state_fips, provider_ruca, apc_desc, bene_cnt,
--      comp_asgn_pymt_cnt, average_medicare_allowed_amt,
--      average_medicare_stnd_amt.
--    - Rename: average_submitted_charges → average_estimated_submitted_charges
--      (to match loader field name).
--
-- ROLLBACK: see 091_rollback.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. hcs_raw.cms_physician_puf — add missing columns for current CMS format
-- ---------------------------------------------------------------------------

ALTER TABLE hcs_raw.cms_physician_puf
    ADD COLUMN IF NOT EXISTS nppes_provider_street1   TEXT,
    ADD COLUMN IF NOT EXISTS nppes_provider_street2   TEXT,
    ADD COLUMN IF NOT EXISTS nppes_provider_state_fips TEXT,
    ADD COLUMN IF NOT EXISTS nppes_provider_ruca       TEXT,
    ADD COLUMN IF NOT EXISTS nppes_provider_country    TEXT;

-- total_submitted_chrg_amt was in migration 085 DDL already; add if absent
ALTER TABLE hcs_raw.cms_physician_puf
    ADD COLUMN IF NOT EXISTS total_submitted_chrg_amt NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS total_medicare_stnd_amt  NUMERIC(18,2);

-- ---------------------------------------------------------------------------
-- 2. hcs_raw.cms_nppes — add missing mailing-address columns
--    (practice-location columns were added in migration 086)
-- ---------------------------------------------------------------------------

ALTER TABLE hcs_raw.cms_nppes
    -- Individual name supplement fields
    ADD COLUMN IF NOT EXISTS provider_middle_name       TEXT,
    ADD COLUMN IF NOT EXISTS provider_name_prefix_text  TEXT,
    ADD COLUMN IF NOT EXISTS provider_name_suffix_text  TEXT,
    -- Mailing address supplemental fields
    ADD COLUMN IF NOT EXISTS provider_first_line_business_mailing_address   TEXT,
    ADD COLUMN IF NOT EXISTS provider_second_line_business_mailing_address  TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_mailing_address_country_code TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_mailing_address_telephone_number TEXT,
    ADD COLUMN IF NOT EXISTS provider_business_mailing_address_fax_number   TEXT;

-- ---------------------------------------------------------------------------
-- 3. hcs_raw.cms_inpatient_puf — add missing columns for current CMS format
-- ---------------------------------------------------------------------------

ALTER TABLE hcs_raw.cms_inpatient_puf
    ADD COLUMN IF NOT EXISTS drg_cd              TEXT,
    ADD COLUMN IF NOT EXISTS provider_state_fips TEXT,
    ADD COLUMN IF NOT EXISTS provider_ruca       TEXT;

-- ---------------------------------------------------------------------------
-- 4. hcs_raw.cms_outpatient_puf — add missing columns for current CMS format
-- ---------------------------------------------------------------------------

ALTER TABLE hcs_raw.cms_outpatient_puf
    ADD COLUMN IF NOT EXISTS provider_name                    TEXT,
    ADD COLUMN IF NOT EXISTS provider_city                    TEXT,
    ADD COLUMN IF NOT EXISTS provider_street_address          TEXT,
    ADD COLUMN IF NOT EXISTS provider_state_fips              TEXT,
    ADD COLUMN IF NOT EXISTS provider_ruca                    TEXT,
    ADD COLUMN IF NOT EXISTS apc_desc                         TEXT,
    ADD COLUMN IF NOT EXISTS bene_cnt                         INTEGER,
    ADD COLUMN IF NOT EXISTS comp_asgn_pymt_cnt               INTEGER,
    ADD COLUMN IF NOT EXISTS average_medicare_allowed_amt     NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS average_medicare_stnd_amt        NUMERIC(18,2);

-- Rename average_submitted_charges → average_estimated_submitted_charges to
-- match the Python loader field name and CMS source column semantics.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_outpatient_puf'
          AND column_name  = 'average_submitted_charges'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'hcs_raw'
          AND table_name   = 'cms_outpatient_puf'
          AND column_name  = 'average_estimated_submitted_charges'
    ) THEN
        ALTER TABLE hcs_raw.cms_outpatient_puf
            RENAME COLUMN average_submitted_charges TO average_estimated_submitted_charges;
    END IF;
END;
$$;

-- If the column already existed under the new name (idempotent re-run), add if missing
ALTER TABLE hcs_raw.cms_outpatient_puf
    ADD COLUMN IF NOT EXISTS average_estimated_submitted_charges NUMERIC(18,2);

-- Rename average_medicare_payments → keep as-is; add average_medicare_payments if absent
ALTER TABLE hcs_raw.cms_outpatient_puf
    ADD COLUMN IF NOT EXISTS average_medicare_payments NUMERIC(18,2);

-- ---------------------------------------------------------------------------
-- 5. hcs_raw.cms_nppes — ensure healthcare_provider_taxonomy_code_2 exists
--    (migration 085 only included code_1 and code_2 was added implicitly; verify)
-- ---------------------------------------------------------------------------

ALTER TABLE hcs_raw.cms_nppes
    ADD COLUMN IF NOT EXISTS healthcare_provider_taxonomy_code_2 TEXT;

-- Also add mailing address columns that 085 omitted from the initial DDL
-- (Practice-location columns were added in migration 086.)
ALTER TABLE hcs_raw.cms_nppes
    ADD COLUMN IF NOT EXISTS provider_first_line_business_mailing_address  TEXT,
    ADD COLUMN IF NOT EXISTS provider_second_line_business_mailing_address TEXT;

-- ---------------------------------------------------------------------------
-- 6. hcs_raw.cms_physician_puf_services — add hcpcs_drug_ind column
--    (migration 086 created the table but omitted the drug indicator flag)
-- ---------------------------------------------------------------------------

ALTER TABLE hcs_raw.cms_physician_puf_services
    ADD COLUMN IF NOT EXISTS hcpcs_drug_ind TEXT;

COMMIT;
