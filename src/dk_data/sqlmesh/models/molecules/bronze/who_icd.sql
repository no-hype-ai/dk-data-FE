-- SQLMesh Model: Bronze WHO ICD Codes
-- Transforms raw WHO ICD-10 API responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name bronze.who_icd,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (icd_code)),
        unique_values(columns := (icd_code))
    ),
    grain icd_code
);

SELECT
    gen_random_uuid() AS id,

    -- ICD code identifiers
    response_body->>'code' AS icd_code,
    response_body->>'title' AS title,
    response_body->>'chapter' AS chapter,
    response_body->>'block_id' AS block_id,
    response_body->>'category' AS category,
    response_body->'includes' AS includes,
    response_body->'excludes' AS excludes,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'who_icd' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.who_icd
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'code' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
