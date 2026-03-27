-- SQLMesh Model: Bronze CMS Hospital Outpatient PUF
-- Typed pass-through from hcs_raw.cms_outpatient_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_outpatient_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (_source_hash, provider_id, apc, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (provider_id, apc, _source_year))
    ),
    grain (_source_hash, provider_id, apc, _source_year)
);

SELECT
    id,
    provider_id,
    apc,
    apc_desc,
    total_services,
    average_submitted_charges,
    average_total_payments,
    average_medicare_payments,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_outpatient_puf;
