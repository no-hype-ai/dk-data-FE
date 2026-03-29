-- SQLMesh Model: Bronze CMS Medicare Inpatient
-- Transforms raw CMS Medicare Inpatient API responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration
--
-- Source: hcs_raw.cms_medicare_inpatient (envelope schema)
-- Grain: one row per (provider_id, drg_code, fiscal_year)

MODEL (
    name hcs_bronze.cms_inpatient,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (record_id)),
        unique_values(columns := (record_id))
    ),
    grain record_id
);

SELECT
    gen_random_uuid() AS record_id,

    -- Provider identity
    response_body->>'provider_id'           AS provider_id,
    response_body->>'provider_name'         AS provider_name,
    response_body->>'provider_city'         AS provider_city,
    response_body->>'provider_state'        AS provider_state,
    response_body->>'provider_zip_code'     AS provider_zip_code,

    -- DRG
    response_body->>'drg_code'              AS drg_code,
    response_body->>'drg_description'       AS drg_description,

    -- Utilization + payment metrics
    (response_body->>'total_discharges')::INTEGER           AS total_discharges,
    (response_body->>'average_covered_charges')::NUMERIC    AS avg_charges,
    (response_body->>'average_total_payments')::NUMERIC     AS avg_payments,
    (response_body->>'average_medicare_payments')::NUMERIC  AS avg_medicare_payments,

    -- Fiscal year
    (response_body->>'fiscal_year')::INTEGER    AS fiscal_year,

    -- Raw source tracking
    response_body AS raw_json,
    id            AS raw_source_id,
    'cms_inpatient' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE         AS processed_to_silver,
    NOW()         AS created_at

FROM (
    SELECT DISTINCT ON (
        response_body->>'provider_id',
        response_body->>'drg_code',
        response_body->>'fiscal_year'
    )
        *
    FROM hcs_raw.cms_medicare_inpatient
    WHERE
        response_status = 200
        AND processed_to_bronze = FALSE
        AND response_body->>'provider_id' IS NOT NULL
        AND request_timestamp BETWEEN @start_dt AND @end_dt
    ORDER BY
        response_body->>'provider_id',
        response_body->>'drg_code',
        response_body->>'fiscal_year',
        request_timestamp DESC
) hcs_raw_cms_inpatient_dedup;
