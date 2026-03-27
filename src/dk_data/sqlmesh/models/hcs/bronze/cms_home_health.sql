-- SQLMesh Model: Bronze CMS Home Health Agency Directory
-- Typed pass-through from hcs_raw.cms_home_health
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_home_health,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (cms_certification_number, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (cms_certification_number, _source_year))
    ),
    grain (cms_certification_number, _source_year)
);

SELECT
    id,
    cms_certification_number,
    provider_name,
    address,
    city,
    state,
    zip_code,
    type_of_ownership,
    offers_nursing_care_services,
    offers_physical_therapy,
    offers_occupational_therapy,
    overall_quality_star_rating,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_home_health;
