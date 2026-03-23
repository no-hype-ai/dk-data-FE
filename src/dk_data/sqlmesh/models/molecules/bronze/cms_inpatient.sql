-- SQLMesh Model: Bronze CMS Medicare Inpatient
-- Transforms raw CMS Medicare inpatient data to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_bronze.cms_inpatient,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (provider_id)),
        unique_values(columns := (record_id))
    ),
    grain record_id
);

SELECT
    gen_random_uuid() AS id,

    -- Record identifiers
    provider_id || '_' || drg_code || '_' || fiscal_year::TEXT AS record_id,
    provider_id,
    drg_code,
    total_discharges,
    average_covered_charges                     AS avg_charges,
    average_total_payments                      AS avg_payments,
    fiscal_year::TEXT                           AS fiscal_year,

    -- Raw source tracking
    NULL::JSONB                                 AS raw_json,
    id::TEXT                                    AS raw_source_id,
    'cms_inpatient'                             AS source,
    _loaded_at,
    _loaded_at                                  AS source_updated_at,
    FALSE                                       AS processed_to_silver,
    NOW()                                       AS created_at

FROM hcs_raw.cms_medicare_inpatient
WHERE
    provider_id IS NOT NULL
    AND _loaded_at BETWEEN @start_dt AND @end_dt;
