-- SQLMesh Model: Bronze CMS Medicare Inpatient
-- Transforms raw CMS Medicare inpatient data responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name bronze.cms_inpatient,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
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
    COALESCE(
        response_body->>'provider_id' || '_' || response_body->>'drg_code' || '_' || response_body->>'fiscal_year',
        gen_random_uuid()::TEXT
    ) AS record_id,
    response_body->>'provider_id' AS provider_id,
    response_body->>'drg_code' AS drg_code,
    (response_body->>'total_discharges')::INTEGER AS total_discharges,
    (response_body->>'avg_charges')::NUMERIC AS avg_charges,
    (response_body->>'avg_payments')::NUMERIC AS avg_payments,
    response_body->>'fiscal_year' AS fiscal_year,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'cms_inpatient' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM hcs_raw.cms_medicare_inpatient
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'provider_id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
