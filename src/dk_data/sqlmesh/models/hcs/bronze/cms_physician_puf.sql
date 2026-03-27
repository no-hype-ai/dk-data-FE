-- SQLMesh Model: Bronze CMS Medicare Physician and Other Practitioners PUF
-- Typed pass-through from hcs_raw.cms_physician_puf
-- Feature: 019-cms-puf-platform-reconciliation (T012)

MODEL (
    name hcs_bronze.cms_physician_puf,
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
    nppes_provider_last_org_name,
    nppes_provider_first_name,
    nppes_provider_mi,
    nppes_credentials,
    nppes_provider_gender,
    nppes_entity_code,
    nppes_provider_city,
    nppes_provider_state,
    nppes_provider_zip,
    provider_type,
    medicare_participation_indicator,
    number_of_hcpcs,
    total_services,
    total_unique_benes,
    total_submitted_chrg_amt,
    total_medicare_allowed_amt,
    total_medicare_payment_amt,
    total_medicare_stnd_amt,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_physician_puf;
