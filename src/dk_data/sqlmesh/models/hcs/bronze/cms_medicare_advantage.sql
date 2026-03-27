-- SQLMesh Model: Bronze CMS Medicare Advantage Plan Directory
-- Typed pass-through from hcs_raw.cms_medicare_advantage
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_medicare_advantage,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (contract_id, plan_id, segment_id, fips_county_code, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (contract_id, plan_id, _source_year))
    ),
    grain (contract_id, plan_id, segment_id, fips_county_code, _source_year)
);

SELECT
    id,
    contract_id,
    plan_id,
    segment_id,
    organization_name,
    plan_name,
    plan_type,
    state,
    county,
    fips_county_code,
    enrolled,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_medicare_advantage;
