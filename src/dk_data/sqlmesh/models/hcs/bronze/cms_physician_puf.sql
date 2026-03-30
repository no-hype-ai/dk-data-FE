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
        not_null(columns := (_source_year))
    ),
    grain (npi, _source_year)
);

SELECT
    id::BIGINT,
    npi::TEXT,
    nppes_provider_last_org_name::TEXT,
    nppes_provider_first_name::TEXT,
    nppes_provider_mi::TEXT,
    nppes_credentials::TEXT,
    nppes_provider_gender::TEXT,
    nppes_entity_code::TEXT,
    nppes_provider_street1::TEXT,
    nppes_provider_street2::TEXT,
    nppes_provider_city::TEXT,
    nppes_provider_state::TEXT,
    nppes_provider_state_fips::TEXT,
    nppes_provider_zip::TEXT,
    nppes_provider_ruca::TEXT,
    nppes_provider_country::TEXT,
    provider_type::TEXT,
    medicare_participation_indicator::TEXT,
    number_of_hcpcs::INTEGER,
    total_services::NUMERIC,
    total_unique_benes::INTEGER,
    total_submitted_chrg_amt::NUMERIC,
    total_medicare_allowed_amt::NUMERIC,
    total_medicare_payment_amt::NUMERIC,
    total_medicare_stnd_amt::NUMERIC,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at::TIMESTAMPTZ,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_physician_puf;
