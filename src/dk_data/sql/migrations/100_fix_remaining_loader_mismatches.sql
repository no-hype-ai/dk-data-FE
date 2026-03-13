-- Fix remaining loader-to-schema mismatches found in smoke test.
-- Feature: 016-cms-puf-datasource-integration

-- =============================================================================
-- 1. raw.cms_open_payments — loader targets this, but 083 created 3 split tables
-- =============================================================================
CREATE TABLE IF NOT EXISTS raw.cms_open_payments (
    record_id               TEXT PRIMARY KEY,
    payment_type            TEXT,
    covered_recipient_npi   TEXT,
    manufacturer_name       TEXT,
    total_amount_usd        NUMERIC,
    date_of_payment         TEXT,
    nature_of_payment       TEXT,
    form_of_payment         TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);
CREATE INDEX IF NOT EXISTS idx_cms_open_payments_npi ON raw.cms_open_payments (covered_recipient_npi);

-- =============================================================================
-- 2. raw.cms_part_d_prescriber — loader uses drug_brand_name, prescriber_* columns
--    Migration 083 has drug_name, generic_name, total_claim_count, etc.
--    Loader also populates drug_name = drug_brand_name for PK compatibility.
-- =============================================================================
ALTER TABLE raw.cms_part_d_prescriber
    ADD COLUMN IF NOT EXISTS drug_brand_name TEXT,
    ADD COLUMN IF NOT EXISTS drug_generic_name TEXT,
    ADD COLUMN IF NOT EXISTS prescriber_last_org_name TEXT,
    ADD COLUMN IF NOT EXISTS prescriber_first_name TEXT,
    ADD COLUMN IF NOT EXISTS prescriber_city TEXT,
    ADD COLUMN IF NOT EXISTS prescriber_state TEXT,
    ADD COLUMN IF NOT EXISTS prescriber_type TEXT,
    ADD COLUMN IF NOT EXISTS total_claims INTEGER,
    ADD COLUMN IF NOT EXISTS total_30day_fills NUMERIC,
    ADD COLUMN IF NOT EXISTS total_beneficiaries INTEGER;

-- =============================================================================
-- 3. raw.cms_hospital_general_info — drop PK so loader can use facility_id
-- =============================================================================
ALTER TABLE raw.cms_hospital_general_info DROP CONSTRAINT IF EXISTS cms_hospital_general_info_pkey;
ALTER TABLE raw.cms_hospital_general_info ALTER COLUMN provider_id DROP NOT NULL;

-- =============================================================================
-- 4. raw.cms_hospital_quality — drop PK so loader can use facility_id
-- =============================================================================
ALTER TABLE raw.cms_hospital_quality DROP CONSTRAINT IF EXISTS cms_hospital_quality_pkey;
ALTER TABLE raw.cms_hospital_quality ALTER COLUMN provider_id DROP NOT NULL;
ALTER TABLE raw.cms_hospital_quality ALTER COLUMN measure_id DROP NOT NULL;

-- =============================================================================
-- 5. raw.cms_ndc — drop PK on ndc, loader uses product_ndc via UNIQUE constraint
-- =============================================================================
ALTER TABLE raw.cms_ndc DROP CONSTRAINT IF EXISTS cms_ndc_pkey;

-- =============================================================================
-- 6. raw.pdb — add _loaded_at column (JSONB envelope table didn't have it)
-- =============================================================================
ALTER TABLE raw.pdb ADD COLUMN IF NOT EXISTS _loaded_at TIMESTAMPTZ DEFAULT now();
