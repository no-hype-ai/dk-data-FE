-- SQLMesh Model: Bronze CMS Imaging PUF
-- Typed pass-through from hcs_raw.cms_imaging_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_imaging_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (hcpcs_cd, modality, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (hcpcs_cd, _source_year))
    ),
    grain (hcpcs_cd, modality, _source_year)
);

SELECT
    id,
    hcpcs_cd,
    hcpcs_desc,
    modality,
    total_providers,
    total_unique_benes,
    total_services,
    average_medicare_allowed_amt,
    average_medicare_payment_amt,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_imaging_puf;
