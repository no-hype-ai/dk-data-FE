-- SQLMesh Model: Bronze CMS Hospital Info
-- Transforms raw CMS Hospital Compare data responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name bronze.cms_hospital_info,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (provider_id)),
        unique_values(columns := (provider_id))
    ),
    grain provider_id
);

SELECT
    gen_random_uuid() AS id,

    -- Hospital identifiers
    response_body->>'provider_id' AS provider_id,
    response_body->>'hospital_name' AS hospital_name,
    response_body->>'city' AS city,
    response_body->>'state' AS state,
    response_body->>'hospital_type' AS hospital_type,
    response_body->>'ownership' AS ownership,
    (response_body->>'rating')::INTEGER AS rating,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'cms_hospital_info' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM raw.cms_hospital_info
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'provider_id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
