-- SQLMesh Model: Bronze CMS Inpatient PUF (All DRGs)
-- Typed pass-through from hcs_raw.cms_inpatient_puf
-- Feature: 019-cms-puf-platform-reconciliation (T012)

MODEL (
    name hcs_bronze.cms_inpatient_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (_source_hash, provider_id, drg_definition, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (provider_id, drg_definition, _source_year))
    ),
    grain (_source_hash, provider_id, drg_definition, _source_year)
);

SELECT
    id,
    drg_definition,
    provider_id,
    provider_name,
    provider_street_address,
    provider_city,
    provider_state,
    provider_zip_code,
    hospital_referral_region_desc,
    total_discharges,
    average_covered_charges,
    average_total_payments,
    average_medicare_payments,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_inpatient_puf;
