-- SQLMesh Model: Bronze CMS Mental Health PUF
-- Typed pass-through from hcs_raw.cms_mental_health_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_mental_health_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (npi, hcpcs_cd, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (npi, hcpcs_cd, _source_year))
    ),
    grain (npi, hcpcs_cd, _source_year)
);

SELECT
    id,
    npi,
    provider_type,
    provider_name,
    provider_city,
    provider_state,
    hcpcs_cd,
    hcpcs_desc,
    total_benes,
    total_services,
    total_medicare_payment_amt,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_mental_health_puf;
