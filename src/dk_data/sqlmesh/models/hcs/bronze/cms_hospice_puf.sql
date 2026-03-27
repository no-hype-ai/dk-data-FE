-- SQLMesh Model: Bronze CMS Hospice PUF
-- Typed pass-through from hcs_raw.cms_hospice_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_hospice_puf,
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
    organization_name,
    address,
    city,
    state,
    zip_code,
    total_medicare_beneficiaries,
    average_length_of_service,
    total_charges,
    total_medicare_allowed_amt,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_hospice_puf;
