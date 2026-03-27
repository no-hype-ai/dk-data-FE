-- SQLMesh Model: Bronze CMS Durable Medical Equipment PUF
-- Typed pass-through from hcs_raw.cms_dme_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_dme_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (npi, hcpcs_cd, provider_type, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (npi, hcpcs_cd, _source_year))
    ),
    grain (npi, hcpcs_cd, provider_type, _source_year)
);

SELECT
    id,
    npi,
    hcpcs_cd,
    hcpcs_desc,
    provider_type,
    supplier_type,
    total_suppliers,
    total_unique_benes,
    total_submitted_chrg_amt,
    total_medicare_allowed_amt,
    total_medicare_payment_amt,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_dme_puf;
