-- SQLMesh Model: Bronze CMS Ordering Providers
-- Typed pass-through from hcs_raw.cms_ordering_providers
-- Raw CMS field names preserved: Rndrng_NPI → rndrng_npi, Rfrd_NPI → rfrd_npi, etc.
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_ordering_providers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (rndrng_npi, rfrd_npi, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (_source_year))
    ),
    grain (rndrng_npi, rfrd_npi, _source_year)
);

SELECT
    id,
    rndrng_npi::TEXT                        AS rndrng_npi,
    rndrng_prvdr_last_org_name::TEXT        AS rndrng_prvdr_last_org_name,
    rndrng_prvdr_first_name::TEXT           AS rndrng_prvdr_first_name,
    rndrng_prvdr_city::TEXT                 AS rndrng_prvdr_city,
    rndrng_prvdr_state_abrvtn::TEXT         AS rndrng_prvdr_state_abrvtn,
    rndrng_prvdr_zip5::TEXT                 AS rndrng_prvdr_zip5,
    rndrng_prvdr_type::TEXT                 AS rndrng_prvdr_type,
    rfrd_npi::TEXT                          AS rfrd_npi,
    rfrd_prvdr_last_org_name::TEXT          AS rfrd_prvdr_last_org_name,
    rfrd_prvdr_type::TEXT                   AS rfrd_prvdr_type,
    tot_srvcs::NUMERIC                      AS tot_srvcs,
    tot_benes::INTEGER                      AS tot_benes,
    tot_mdcr_alowd_amt::NUMERIC             AS tot_mdcr_alowd_amt,
    tot_mdcr_pymt_amt::NUMERIC              AS tot_mdcr_pymt_amt,
    _source_year::INTEGER,
    _source_hash::TEXT,
    _source_file::TEXT,
    _loaded_at,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_ordering_providers;
