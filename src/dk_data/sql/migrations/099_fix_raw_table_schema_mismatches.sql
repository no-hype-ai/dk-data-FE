-- Fix schema mismatches between migration 083 table definitions and source loaders.
-- The loaders/fetchers use consistent column names that differ from the migration.
-- This migration ALTERs tables to add missing columns so loaders can INSERT successfully.
-- Feature: 016-cms-puf-datasource-integration

-- =============================================================================
-- 1. raw.cms_care_compare — table doesn't exist (083 created cms_care_compare_physicians)
--    Loader expects facility-level table with facility_id PK
-- =============================================================================
CREATE TABLE IF NOT EXISTS raw.cms_care_compare (
    facility_id             TEXT PRIMARY KEY,
    facility_name           TEXT,
    address                 TEXT,
    city                    TEXT,
    state                   TEXT,
    zip_code                TEXT,
    county_name             TEXT,
    phone_number            TEXT,
    hospital_type           TEXT,
    hospital_ownership      TEXT,
    emergency_services      TEXT,
    overall_rating          TEXT,
    _loaded_at              TIMESTAMPTZ DEFAULT now(),
    _source_file            TEXT,
    _source_hash            TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_care_compare_state ON raw.cms_care_compare (state);

-- =============================================================================
-- 2. raw.cms_hospital_general_info — loader uses facility_id, facility_name, etc.
--    Migration has provider_id, hospital_name, ownership
-- =============================================================================
ALTER TABLE raw.cms_hospital_general_info
    ADD COLUMN IF NOT EXISTS facility_id TEXT,
    ADD COLUMN IF NOT EXISTS facility_name TEXT,
    ADD COLUMN IF NOT EXISTS county_name TEXT,
    ADD COLUMN IF NOT EXISTS phone_number TEXT,
    ADD COLUMN IF NOT EXISTS hospital_ownership TEXT,
    ADD COLUMN IF NOT EXISTS emergency_services TEXT;

-- Allow facility-level upserts (loader does ON CONFLICT (facility_id))
ALTER TABLE raw.cms_hospital_general_info
    ADD CONSTRAINT uq_cms_hospital_general_info_facility_id UNIQUE (facility_id);

-- =============================================================================
-- 3. raw.cms_hospital_quality — loader uses facility_id + star ratings
--    Migration has (provider_id, measure_id) composite PK with measure scores
--    Add loader columns so facility-level star ratings can be stored too
-- =============================================================================
ALTER TABLE raw.cms_hospital_quality
    ADD COLUMN IF NOT EXISTS facility_id TEXT,
    ADD COLUMN IF NOT EXISTS facility_name TEXT,
    ADD COLUMN IF NOT EXISTS overall_rating TEXT,
    ADD COLUMN IF NOT EXISTS mortality_rating TEXT,
    ADD COLUMN IF NOT EXISTS safety_rating TEXT,
    ADD COLUMN IF NOT EXISTS readmission_rating TEXT,
    ADD COLUMN IF NOT EXISTS patient_experience_rating TEXT,
    ADD COLUMN IF NOT EXISTS timeliness_rating TEXT;

-- Allow facility-level upserts (loader does ON CONFLICT (facility_id))
ALTER TABLE raw.cms_hospital_quality
    ADD CONSTRAINT uq_cms_hospital_quality_facility_id UNIQUE (facility_id);

-- =============================================================================
-- 4. raw.cms_ndc — loader uses product_ndc, brand_name, generic_name, marketing_category
--    Migration has ndc, proprietary_name, nonproprietary_name
-- =============================================================================
ALTER TABLE raw.cms_ndc
    ADD COLUMN IF NOT EXISTS product_ndc TEXT,
    ADD COLUMN IF NOT EXISTS brand_name TEXT,
    ADD COLUMN IF NOT EXISTS generic_name TEXT,
    ADD COLUMN IF NOT EXISTS marketing_category TEXT;

-- Allow upserts keyed on product_ndc (loader does ON CONFLICT (product_ndc))
ALTER TABLE raw.cms_ndc
    ADD CONSTRAINT uq_cms_ndc_product_ndc UNIQUE (product_ndc);

-- =============================================================================
-- 5. raw.cms_nppes — loader uses entity_type_code, provider_* column names
--    Migration has entity_type, name_first, name_last, etc.
-- =============================================================================
ALTER TABLE raw.cms_nppes
    ADD COLUMN IF NOT EXISTS entity_type_code TEXT,
    ADD COLUMN IF NOT EXISTS provider_organization_name TEXT,
    ADD COLUMN IF NOT EXISTS provider_last_name TEXT,
    ADD COLUMN IF NOT EXISTS provider_first_name TEXT,
    ADD COLUMN IF NOT EXISTS provider_credential_text TEXT,
    ADD COLUMN IF NOT EXISTS provider_enumeration_date TEXT,
    ADD COLUMN IF NOT EXISTS provider_gender_code TEXT,
    ADD COLUMN IF NOT EXISTS taxonomy_code_1 TEXT;

-- =============================================================================
-- 6. raw.cms_nucc — loader uses taxonomy_type, migration has provider_type
-- =============================================================================
ALTER TABLE raw.cms_nucc
    ADD COLUMN IF NOT EXISTS taxonomy_type TEXT;

-- =============================================================================
-- 7. raw.cms_part_b_spending — loader uses brand_name, generic_name
--    Migration has hcpcs_description, avg_cost_per_claim
-- =============================================================================
ALTER TABLE raw.cms_part_b_spending
    ADD COLUMN IF NOT EXISTS brand_name TEXT,
    ADD COLUMN IF NOT EXISTS generic_name TEXT;

-- =============================================================================
-- 8. raw.cms_pos — loader uses street_address, provider_type, beds, ownership_type
--    Migration has address, facility_type, bed_count
-- =============================================================================
ALTER TABLE raw.cms_pos
    ADD COLUMN IF NOT EXISTS street_address TEXT,
    ADD COLUMN IF NOT EXISTS provider_type TEXT,
    ADD COLUMN IF NOT EXISTS beds INTEGER,
    ADD COLUMN IF NOT EXISTS ownership_type TEXT;

-- =============================================================================
-- 9. raw.pdb — migration 028 created JSONB envelope table, loader expects
--    structured columns (pdb_id, title, method, resolution, deposit_date)
--    Add structured columns alongside the existing JSONB envelope
-- =============================================================================
ALTER TABLE raw.pdb
    ADD COLUMN IF NOT EXISTS pdb_id TEXT,
    ADD COLUMN IF NOT EXISTS title TEXT,
    ADD COLUMN IF NOT EXISTS method TEXT,
    ADD COLUMN IF NOT EXISTS resolution NUMERIC,
    ADD COLUMN IF NOT EXISTS deposit_date DATE,
    ADD COLUMN IF NOT EXISTS raw_response JSONB,
    ADD COLUMN IF NOT EXISTS _source_file TEXT,
    ADD COLUMN IF NOT EXISTS _source_hash TEXT;

-- Allow structured upserts (loader does ON CONFLICT (pdb_id))
ALTER TABLE raw.pdb
    ADD CONSTRAINT uq_pdb_pdb_id UNIQUE (pdb_id);
