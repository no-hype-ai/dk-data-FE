-- SQLMesh Model: Bronze CMS Medicare Utilization PUF
-- Typed pass-through from hcs_raw.cms_utilization_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_utilization_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (service_category, setting_of_care, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (service_category, _source_year))
    ),
    grain (service_category, setting_of_care, _source_year)
);

SELECT
    id,
    service_category,
    setting_of_care,
    total_services,
    total_unique_benes,
    total_medicare_payment,
    per_capita_payment,
    services_per_1000_benes,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_utilization_puf;
