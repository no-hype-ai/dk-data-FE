-- SQLMesh Model: Bronze CMS Medicare Advantage Enrollment
-- Typed pass-through from hcs_raw.cms_medicare_advantage
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Raw columns: contract_id (TEXT), organization_name, organization_type, plan_id,
--   plan_name, segment_id, enrollment_data_period, fips_cd (TEXT),
--   state_fips (TEXT), county_fips (TEXT),
--   enrollment (INTEGER), avg_age (NUMERIC), pct_female (NUMERIC),
--   avg_risk_score (NUMERIC), ma_participation_rate (NUMERIC), star_rating (NUMERIC)

MODEL (
    name hcs_bronze.cms_medicare_advantage,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (contract_id, plan_id, fips_cd, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (contract_id, plan_id, _source_year))
    ),
    grain (contract_id, plan_id, fips_cd, _source_year)
);

SELECT
    id::BIGINT,
    contract_id::TEXT,
    organization_name::TEXT,
    organization_type::TEXT,
    plan_id::TEXT,
    plan_name::TEXT,
    segment_id::TEXT,
    enrollment_data_period::TEXT,
    fips_cd::TEXT,
    state_fips::TEXT,
    county_fips::TEXT,
    enrollment::INTEGER,
    avg_age::NUMERIC,
    pct_female::NUMERIC,
    avg_risk_score::NUMERIC,
    ma_participation_rate::NUMERIC,
    star_rating::NUMERIC,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at::TIMESTAMPTZ,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_medicare_advantage;
