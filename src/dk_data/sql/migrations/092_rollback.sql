-- Migration 092 Rollback: Restore hcs_raw tables to migration 085 state
-- WARNING: This drops all data loaded under the new schema.
-- Run ONLY if rolling back migration 092.

BEGIN;

DROP TABLE IF EXISTS hcs_raw.cms_mental_health_puf CASCADE;
CREATE TABLE hcs_raw.cms_mental_health_puf (
    id BIGSERIAL PRIMARY KEY,
    npi TEXT, provider_type TEXT, provider_name TEXT,
    provider_city TEXT, provider_state TEXT,
    hcpcs_cd TEXT, hcpcs_desc TEXT,
    total_benes INTEGER, total_services NUMERIC(18,2),
    total_medicare_payment_amt NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_opioid_puf CASCADE;
CREATE TABLE hcs_raw.cms_opioid_puf (
    id BIGSERIAL PRIMARY KEY,
    state TEXT, county TEXT, fips TEXT,
    opioid_prescribing_rate NUMERIC(10,4),
    opioid_prescriptions INTEGER, total_prescriptions INTEGER,
    population INTEGER,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (fips, _source_year)
);

DROP TABLE IF EXISTS hcs_raw.cms_telehealth_puf CASCADE;
CREATE TABLE hcs_raw.cms_telehealth_puf (
    id BIGSERIAL PRIMARY KEY,
    npi TEXT, provider_type TEXT,
    telehealth_services INTEGER, total_unique_benes INTEGER,
    total_telehealth_payment NUMERIC(18,2),
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS hcs_raw.cms_medicare_advantage CASCADE;
CREATE TABLE hcs_raw.cms_medicare_advantage (
    id BIGSERIAL PRIMARY KEY,
    contract_id TEXT, plan_id TEXT, segment_id TEXT,
    organization_name TEXT, plan_name TEXT, plan_type TEXT,
    state TEXT, county TEXT, fips_county_code TEXT,
    enrolled INTEGER,
    _source_year INTEGER NOT NULL, _source_hash TEXT NOT NULL,
    _source_file TEXT, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
