-- Migration 087: Add UNIQUE constraints to hcs_raw tables lacking deduplication
-- Feature: 019-cms-puf-platform-reconciliation
-- Date: 2026-03-27
--
-- Adds UNIQUE constraints to the 15 hcs_raw tables that were created without them
-- in migration 085. Uses DO blocks to avoid errors if constraints already exist.
-- Also adds UNIQUE constraints to the new bronze/silver tables.
--
-- Run: doppler run -- python -m dk_data.scripts.run_migration src/dk_data/sql/migrations/087_hcs_unique_constraints.sql

BEGIN;

-- ============================================================================
-- 1. UNIQUE CONSTRAINTS FOR HCS_RAW TABLES (missing from migration 085)
-- ============================================================================

-- cms_open_payments: physician × payment date × manufacturer × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_open_payments_key'
          AND conrelid = 'hcs_raw.cms_open_payments'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_open_payments
            ADD CONSTRAINT uq_cms_open_payments_key
            UNIQUE (physician_profile_id, date_of_payment, applicable_manufacturer_or_gpo_name, _source_year);
    END IF;
END $$;

-- cms_medicare_advantage: contract × plan × segment × county × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_medicare_advantage_key'
          AND conrelid = 'hcs_raw.cms_medicare_advantage'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_medicare_advantage
            ADD CONSTRAINT uq_cms_medicare_advantage_key
            UNIQUE (contract_id, plan_id, segment_id, fips_county_code, _source_year);
    END IF;
END $$;

-- cms_medicaid_drug_spending: state × drug × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_medicaid_drug_spending_key'
          AND conrelid = 'hcs_raw.cms_medicaid_drug_spending'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_medicaid_drug_spending
            ADD CONSTRAINT uq_cms_medicaid_drug_spending_key
            UNIQUE (state_id, drug_name, labeler_name, _source_year);
    END IF;
END $$;

-- cms_dme_puf: NPI × HCPCS × year (DME suppliers)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_dme_puf_key'
          AND conrelid = 'hcs_raw.cms_dme_puf'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_dme_puf
            ADD CONSTRAINT uq_cms_dme_puf_key
            UNIQUE (npi, hcpcs_cd, provider_type, _source_year);
    END IF;
END $$;

-- cms_home_health: provider × HH service code × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_home_health_key'
          AND conrelid = 'hcs_raw.cms_home_health'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_home_health
            ADD CONSTRAINT uq_cms_home_health_key
            UNIQUE (provider_id, hh_srvc_cd, _source_year);
    END IF;
END $$;

-- cms_hospice_puf: provider × hospice service code × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_hospice_puf_key'
          AND conrelid = 'hcs_raw.cms_hospice_puf'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_hospice_puf
            ADD CONSTRAINT uq_cms_hospice_puf_key
            UNIQUE (provider_id, hspce_cd, _source_year);
    END IF;
END $$;

-- cms_snf_puf: provider × RUG code × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_snf_puf_key'
          AND conrelid = 'hcs_raw.cms_snf_puf'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_snf_puf
            ADD CONSTRAINT uq_cms_snf_puf_key
            UNIQUE (provider_id, rug_cd, _source_year);
    END IF;
END $$;

-- cms_referring_providers: referring × referred × year (aggregate pair)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_referring_providers_key'
          AND conrelid = 'hcs_raw.cms_referring_providers'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_referring_providers
            ADD CONSTRAINT uq_cms_referring_providers_key
            UNIQUE (referring_npi, referred_to_npi, _source_year);
    END IF;
END $$;

-- cms_ordering_providers: ordering × performing × HCPCS × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_ordering_providers_key'
          AND conrelid = 'hcs_raw.cms_ordering_providers'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_ordering_providers
            ADD CONSTRAINT uq_cms_ordering_providers_key
            UNIQUE (ordering_npi, performing_npi, hcpcs_cd, _source_year);
    END IF;
END $$;

-- cms_lab_services: NPI × HCPCS × year (provider-level)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_lab_services_key'
          AND conrelid = 'hcs_raw.cms_lab_services'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_lab_services
            ADD CONSTRAINT uq_cms_lab_services_key
            UNIQUE (npi, hcpcs_cd, _source_year);
    END IF;
END $$;

-- cms_imaging_puf: NPI × HCPCS × year (provider-level, no modality in source)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_imaging_puf_key'
          AND conrelid = 'hcs_raw.cms_imaging_puf'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_imaging_puf
            ADD CONSTRAINT uq_cms_imaging_puf_key
            UNIQUE (npi, hcpcs_cd, _source_year);
    END IF;
END $$;

-- cms_mental_health_puf: NPI × HCPCS × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_mental_health_puf_key'
          AND conrelid = 'hcs_raw.cms_mental_health_puf'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_mental_health_puf
            ADD CONSTRAINT uq_cms_mental_health_puf_key
            UNIQUE (npi, hcpcs_cd, _source_year);
    END IF;
END $$;

-- cms_telehealth_puf: NPI × year (one telehealth row per provider per year)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_telehealth_puf_key'
          AND conrelid = 'hcs_raw.cms_telehealth_puf'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_telehealth_puf
            ADD CONSTRAINT uq_cms_telehealth_puf_key
            UNIQUE (npi, _source_year);
    END IF;
END $$;

-- cms_chronic_conditions: geo × age × condition × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_chronic_conditions_key'
          AND conrelid = 'hcs_raw.cms_chronic_conditions'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_chronic_conditions
            ADD CONSTRAINT uq_cms_chronic_conditions_key
            UNIQUE (bene_geo_cd, bene_age_lvl, chronic_condition, _source_year);
    END IF;
END $$;

-- cms_dual_eligible: state × age × race × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_dual_eligible_key'
          AND conrelid = 'hcs_raw.cms_dual_eligible'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_dual_eligible
            ADD CONSTRAINT uq_cms_dual_eligible_key
            UNIQUE (state, bene_age_lvl, bene_race_cd, _source_year);
    END IF;
END $$;

-- cms_claim_type_puf: claim type × service category × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_claim_type_puf_key'
          AND conrelid = 'hcs_raw.cms_claim_type_puf'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_claim_type_puf
            ADD CONSTRAINT uq_cms_claim_type_puf_key
            UNIQUE (claim_type, service_category, _source_year);
    END IF;
END $$;

-- cms_utilization_puf: service category × setting × year
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_cms_utilization_puf_key'
          AND conrelid = 'hcs_raw.cms_utilization_puf'::regclass
    ) THEN
        ALTER TABLE hcs_raw.cms_utilization_puf
            ADD CONSTRAINT uq_cms_utilization_puf_key
            UNIQUE (service_category, setting_of_care, _source_year);
    END IF;
END $$;

-- ============================================================================
-- 2. INDEXES FOR QUERY PERFORMANCE ON HIGH-TRAFFIC COLUMNS
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_cms_referring_providers_referring_npi
    ON hcs_raw.cms_referring_providers (referring_npi, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_referring_providers_referred_to_npi
    ON hcs_raw.cms_referring_providers (referred_to_npi, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_ordering_providers_ordering_npi
    ON hcs_raw.cms_ordering_providers (ordering_npi, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_mental_health_puf_npi
    ON hcs_raw.cms_mental_health_puf (npi, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_telehealth_puf_npi
    ON hcs_raw.cms_telehealth_puf (npi, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_dme_puf_npi
    ON hcs_raw.cms_dme_puf (npi, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_hospice_puf_provider
    ON hcs_raw.cms_hospice_puf (provider_id, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_home_health_provider
    ON hcs_raw.cms_home_health (provider_id, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_snf_puf_provider
    ON hcs_raw.cms_snf_puf (provider_id, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_lab_services_npi
    ON hcs_raw.cms_lab_services (npi, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_imaging_puf_npi
    ON hcs_raw.cms_imaging_puf (npi, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_chronic_conditions_geo
    ON hcs_raw.cms_chronic_conditions (bene_geo_cd, _source_year);

CREATE INDEX IF NOT EXISTS idx_cms_geographic_variation_geo
    ON hcs_raw.cms_geographic_variation (bene_geo_cd, _source_year);

COMMIT;
