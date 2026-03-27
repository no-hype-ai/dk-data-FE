-- SQLMesh Model: Bronze CMS Ordering Providers
-- Typed pass-through from hcs_raw.cms_ordering_providers
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_ordering_providers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (ordering_npi, performing_npi, hcpcs_cd, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (ordering_npi, _source_year))
    ),
    grain (ordering_npi, performing_npi, hcpcs_cd, _source_year)
);

SELECT
    id,
    ordering_npi,
    performing_npi,
    ordering_provider_last_name,
    ordering_provider_first_name,
    ordering_provider_type,
    hcpcs_cd,
    total_services,
    total_unique_benes,
    total_submitted_chrg_amt,
    total_medicare_payment_amt,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_ordering_providers;
