-- SQLMesh Model: Bronze CMS Inpatient PUF
-- Transforms flat hcs_raw.cms_inpatient_puf table to Bronze typed columns.
-- Source: hcs_raw.cms_inpatient_puf (loaded by cms_inpatient_puf.py CronJob)
-- Part of: 015-assessment-dashboard-integration / 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_inpatient,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key record_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (provider_id))
    ),
    grain record_id
);

SELECT
    gen_random_uuid() AS id,

    -- Record identifiers
    COALESCE(
        provider_id || '_' || drg_cd || '_' || _source_year::TEXT,
        gen_random_uuid()::TEXT
    ) AS record_id,
    -- Raw column names retained verbatim per FR-001
    provider_id::TEXT                                                       AS provider_id,
    provider_name::TEXT                                                     AS provider_name,
    provider_street_address::TEXT                                           AS provider_street_address,
    provider_city::TEXT                                                     AS provider_city,
    provider_state::TEXT                                                    AS provider_state,
    provider_state_fips::TEXT                                               AS provider_state_fips,
    provider_zip_code::TEXT                                                 AS provider_zip_code,
    provider_ruca::TEXT                                                     AS provider_ruca,
    hospital_referral_region_desc::TEXT                                     AS hospital_referral_region_desc,
    drg_cd::TEXT                                                            AS drg_cd,
    drg_definition::TEXT                                                    AS drg_definition,
    total_discharges::INTEGER                                               AS total_discharges,
    average_covered_charges::NUMERIC                                        AS average_covered_charges,
    average_total_payments::NUMERIC                                         AS average_total_payments,
    average_medicare_payments::NUMERIC                                      AS average_medicare_payments,
    _source_year::TEXT                                                      AS fiscal_year,

    -- Raw source tracking
    id::BIGINT AS raw_source_id,
    'cms_inpatient_puf' AS source,
    _loaded_at::TIMESTAMPTZ AS request_timestamp,
    _loaded_at::TIMESTAMPTZ AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM hcs_raw.cms_inpatient_puf
WHERE
    provider_id IS NOT NULL
    AND _loaded_at BETWEEN @start_dt AND @end_dt;
