-- SQLMesh Model: Bronze CMS Telehealth PUF
-- Typed pass-through from hcs_raw.cms_telehealth_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_telehealth_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (npi, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (npi, _source_year))
    ),
    grain (npi, _source_year)
);

SELECT
    id,
    npi,
    provider_type,
    telehealth_services,
    total_unique_benes,
    total_telehealth_payment,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_telehealth_puf;
