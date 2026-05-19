-- =============================================================================
-- Rollback for Migration 093: HCS 7-Source Raw Table Schema Fix
-- Feature: 019-cms-puf-platform-reconciliation
-- =============================================================================
-- This migration dropped and recreated 7 tables. A true rollback would restore
-- the old schema from migration 085. Since the old schemas had wrong column names,
-- this rollback restores the migration 085 versions for emergency recovery only.
-- Any data loaded under 093 will be lost.
-- =============================================================================

BEGIN;

-- Drop the 093 versions
DROP TABLE IF EXISTS hcs_raw.cms_chronic_conditions  CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_dual_eligible        CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_enrollment_puf       CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_utilization_puf      CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_claim_type_puf       CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_referring_providers  CASCADE;
DROP TABLE IF EXISTS hcs_raw.cms_ordering_providers   CASCADE;

-- Restore migration 085 versions (old schema, wrong field names)
CREATE TABLE hcs_raw.cms_chronic_conditions (
    id BIGSERIAL PRIMARY KEY,
    bene_geo_lvl TEXT, bene_geo_cd TEXT, bene_geo_desc TEXT,
    bene_age_lvl TEXT, chronic_condition TEXT, prevalence NUMERIC(10,4),
    total_medicare_payment NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE hcs_raw.cms_dual_eligible (
    id BIGSERIAL PRIMARY KEY,
    state TEXT, bene_age_lvl TEXT, bene_race_cd TEXT,
    dual_benes INTEGER, non_dual_benes INTEGER,
    dual_pymt_pc NUMERIC(18,2), non_dual_pymt_pc NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE hcs_raw.cms_enrollment_puf (
    id BIGSERIAL PRIMARY KEY,
    state TEXT, county TEXT, fips TEXT,
    total_beneficiaries INTEGER, aged_esrd_benes INTEGER,
    disabled_benes INTEGER, esrd_benes INTEGER, aged_benes INTEGER,
    orig_reason_entitlement TEXT,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (fips, _source_year)
);

CREATE TABLE hcs_raw.cms_utilization_puf (
    id BIGSERIAL PRIMARY KEY,
    service_category TEXT, setting_of_care TEXT,
    total_services BIGINT, total_unique_benes INTEGER,
    total_medicare_payment NUMERIC(18,2), per_capita_payment NUMERIC(18,2),
    services_per_1000_benes NUMERIC(10,4),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE hcs_raw.cms_claim_type_puf (
    id BIGSERIAL PRIMARY KEY,
    claim_type TEXT, service_category TEXT,
    total_claims BIGINT, total_beneficiaries INTEGER,
    total_allowed_amount NUMERIC(18,2), total_payment_amount NUMERIC(18,2),
    avg_payment_per_claim NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE hcs_raw.cms_referring_providers (
    id BIGSERIAL PRIMARY KEY,
    referring_npi TEXT, referred_to_npi TEXT,
    provider_last_org_name TEXT, provider_first_name TEXT,
    provider_type TEXT, provider_city TEXT, provider_state TEXT,
    referral_count INTEGER, unique_benes INTEGER,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE hcs_raw.cms_ordering_providers (
    id BIGSERIAL PRIMARY KEY,
    ordering_npi TEXT, performing_npi TEXT,
    ordering_provider_last_name TEXT, ordering_provider_first_name TEXT,
    ordering_provider_type TEXT,
    hcpcs_cd TEXT, total_services INTEGER, total_unique_benes INTEGER,
    total_submitted_chrg_amt NUMERIC(18,2), total_medicare_payment_amt NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
