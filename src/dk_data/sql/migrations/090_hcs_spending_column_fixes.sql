-- =============================================================================
-- Migration 090: HCS Spending Table Column Name Fixes
-- Feature: 019-cms-puf-platform-reconciliation
-- Date: 2026-03-27
-- =============================================================================
-- Migration 085 created hcs_raw.cms_part_d_spending, hcs_raw.cms_part_b_spending,
-- and hcs_raw.cms_medicaid_drug_spending with incorrect column names that did not
-- match the actual CMS API field names. This migration renames columns to match
-- the exact CMS field names (snake_case of PascalCase API names).
--
-- Part D:   tot_drug_cst → tot_spndng, remove mftr_name, tot_30day_fills,
--           avg_spnd_per_30day_fills; add tot_dsg_unts, avg_spnd_per_dsg_unt_wghtd,
--           outlier_flag
-- Part B:   remove provider_type, tot_srvcs, avg_submitted_chrg_amt,
--           avg_allowed_amt, tot_allowed_amt, tot_mdcr_pymt_amt,
--           avg_mdcr_pymt_amt, avg_mdcr_allowed_amt, hcpcs_drug_indicator;
--           add mftr_name, tot_spndng, tot_dsg_unts, tot_clms,
--           avg_spnd_per_dsg_unt, avg_spnd_per_clm, avg_spnd_per_bene, outlier_flag
-- Medicaid: replace old schema (state_id, state_name, drug_name, labeler_name)
--           with correct CMS field schema (brnd_name, gnrc_name, tot_mftr,
--           util_type, tot_spndng, medicaid_spndng_per_dosage_unit,
--           medicaid_spndng_per_prescription, unit_type, tot_dosage_units,
--           tot_prescriptions, tot_benes)
--
-- ROLLBACK: see 090_rollback.sql
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. hcs_raw.cms_part_d_spending
-- =============================================================================

-- Remove wrong columns
ALTER TABLE hcs_raw.cms_part_d_spending
    DROP COLUMN IF EXISTS mftr_name,
    DROP COLUMN IF EXISTS tot_30day_fills,
    DROP COLUMN IF EXISTS avg_spnd_per_30day_fills;

-- Rename tot_drug_cst → tot_spndng (CMS field: Tot_Spndng) — skip if already renamed
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='hcs_raw' AND table_name='cms_part_d_spending' AND column_name='tot_drug_cst') THEN
        ALTER TABLE hcs_raw.cms_part_d_spending RENAME COLUMN tot_drug_cst TO tot_spndng;
    END IF;
END;
$$;

-- Add missing correct columns
ALTER TABLE hcs_raw.cms_part_d_spending
    ADD COLUMN IF NOT EXISTS tot_dsg_unts             NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS avg_spnd_per_dsg_unt_wghtd NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS outlier_flag             TEXT;

COMMENT ON TABLE hcs_raw.cms_part_d_spending IS
    'CMS Medicare Part D Drug Spending by Drug PUF. '
    'CMS fields: Brnd_Name, Gnrc_Name, Tot_Mftr, Tot_Spndng, Tot_Dsg_Unts, '
    'Tot_Clms, Tot_Benes, Avg_Spnd_Per_Dsg_Unt_Wghtd, Avg_Spnd_Per_Clm, '
    'Avg_Spnd_Per_Bene, Outlier_Flag';

-- =============================================================================
-- 2. hcs_raw.cms_part_b_spending
-- =============================================================================

-- Remove all wrong columns from the 085 schema
ALTER TABLE hcs_raw.cms_part_b_spending
    DROP COLUMN IF EXISTS provider_type,
    DROP COLUMN IF EXISTS tot_srvcs,
    DROP COLUMN IF EXISTS avg_submitted_chrg_amt,
    DROP COLUMN IF EXISTS avg_allowed_amt,
    DROP COLUMN IF EXISTS tot_allowed_amt,
    DROP COLUMN IF EXISTS tot_mdcr_pymt_amt,
    DROP COLUMN IF EXISTS avg_mdcr_pymt_amt,
    DROP COLUMN IF EXISTS avg_mdcr_allowed_amt,
    DROP COLUMN IF EXISTS hcpcs_drug_indicator;

-- Add correct CMS field columns
ALTER TABLE hcs_raw.cms_part_b_spending
    ADD COLUMN IF NOT EXISTS mftr_name                TEXT,
    ADD COLUMN IF NOT EXISTS tot_spndng               NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS tot_dsg_unts             NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS tot_clms                 BIGINT,
    ADD COLUMN IF NOT EXISTS avg_spnd_per_dsg_unt     NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS avg_spnd_per_clm         NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS avg_spnd_per_bene        NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS outlier_flag             TEXT;

-- tot_benes already exists in 085 schema with correct type; keep it.

COMMENT ON TABLE hcs_raw.cms_part_b_spending IS
    'CMS Medicare Part B Drug Spending by Manufacturer PUF. '
    'CMS fields: HCPCS_Cd, HCPCS_Desc, Tot_Mftr, Mftr_Name, Tot_Spndng, '
    'Tot_Dsg_Unts, Tot_Benes, Tot_Clms, Avg_Spnd_Per_Dsg_Unt, Avg_Spnd_Per_Clm, '
    'Avg_Spnd_Per_Bene, Outlier_Flag';

-- =============================================================================
-- 3. hcs_raw.cms_medicaid_drug_spending
-- =============================================================================

-- Remove all wrong columns from the 085 schema
ALTER TABLE hcs_raw.cms_medicaid_drug_spending
    DROP COLUMN IF EXISTS state_id,
    DROP COLUMN IF EXISTS state_name,
    DROP COLUMN IF EXISTS drug_name,
    DROP COLUMN IF EXISTS labeler_name;

-- Add correct CMS field columns
ALTER TABLE hcs_raw.cms_medicaid_drug_spending
    ADD COLUMN IF NOT EXISTS brnd_name                         TEXT,
    ADD COLUMN IF NOT EXISTS gnrc_name                         TEXT,
    ADD COLUMN IF NOT EXISTS tot_mftr                          TEXT,
    ADD COLUMN IF NOT EXISTS util_type                         TEXT,
    ADD COLUMN IF NOT EXISTS tot_spndng                        NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS medicaid_spndng_per_dosage_unit   NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS medicaid_spndng_per_prescription  NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS unit_type                         TEXT,
    ADD COLUMN IF NOT EXISTS tot_dosage_units                  NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS tot_prescriptions                 NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS tot_benes                         NUMERIC(18,2);

-- Update UNIQUE constraint to match new conflict_columns in loader
DO $$
BEGIN
    -- Drop old constraint if it exists (columns no longer present)
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_schema = 'hcs_raw'
          AND table_name = 'cms_medicaid_drug_spending'
          AND constraint_type = 'UNIQUE'
          AND constraint_name != 'cms_medicaid_drug_spending_pkey'
    ) THEN
        EXECUTE (
            SELECT 'ALTER TABLE hcs_raw.cms_medicaid_drug_spending DROP CONSTRAINT ' || constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'hcs_raw'
              AND table_name = 'cms_medicaid_drug_spending'
              AND constraint_type = 'UNIQUE'
              AND constraint_name != 'cms_medicaid_drug_spending_pkey'
            LIMIT 1
        );
    END IF;
END;
$$;

ALTER TABLE hcs_raw.cms_medicaid_drug_spending
    ADD CONSTRAINT cms_medicaid_drug_spending_uniq
    UNIQUE (_source_hash, gnrc_name, util_type, _source_year);

COMMENT ON TABLE hcs_raw.cms_medicaid_drug_spending IS
    'CMS Medicaid Drug Spending by Drug and State PUF. '
    'CMS fields: Brnd_Name, Gnrc_Name, Tot_Mftr, Util_Type, Tot_Spndng, '
    'Medicaid_Spndng_Per_Dosage_Unit, Medicaid_Spndng_Per_Prescription, '
    'Unit_Type, Tot_Dosage_Units, Tot_Prescriptions, Tot_Benes';

COMMIT;
