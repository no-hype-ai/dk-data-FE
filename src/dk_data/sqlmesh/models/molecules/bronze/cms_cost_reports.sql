-- SQLMesh Model: Bronze CMS Cost Reports
-- Transforms raw CMS Hospital Cost Report data to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name bronze.cms_cost_reports,
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
        response_body->>'provider_id' || '_' || response_body->>'fiscal_year',
        gen_random_uuid()::TEXT
    ) AS record_id,
    response_body->>'provider_id' AS provider_id,
    response_body->>'fiscal_year' AS fiscal_year,
    (response_body->>'total_costs')::NUMERIC AS total_costs,
    (response_body->>'net_revenue')::NUMERIC AS net_revenue,
    (response_body->>'operating_margin')::NUMERIC AS operating_margin,
    (response_body->>'bed_count')::INTEGER AS bed_count,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'cms_cost_reports' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM raw.cms_cost_reports
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'provider_id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
