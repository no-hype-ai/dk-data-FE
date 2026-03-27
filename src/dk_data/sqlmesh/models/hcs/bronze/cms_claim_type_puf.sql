-- SQLMesh Model: Bronze CMS Medicare Claims by Type PUF
-- Typed pass-through from hcs_raw.cms_claim_type_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_claim_type_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (claim_type, service_category, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (claim_type, _source_year))
    ),
    grain (claim_type, service_category, _source_year)
);

SELECT
    id,
    claim_type,
    service_category,
    total_claims,
    total_beneficiaries,
    total_allowed_amount,
    total_payment_amount,
    avg_payment_per_claim,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_claim_type_puf;
