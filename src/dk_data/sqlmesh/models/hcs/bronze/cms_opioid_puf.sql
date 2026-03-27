-- SQLMesh Model: Bronze CMS Opioid Prescribing Map
-- Typed pass-through from hcs_raw.cms_opioid_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_opioid_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (fips, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (fips, _source_year))
    ),
    grain (fips, _source_year)
);

SELECT
    id,
    state,
    county,
    fips,
    opioid_prescribing_rate,
    opioid_prescriptions,
    total_prescriptions,
    population,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_opioid_puf;
