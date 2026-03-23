-- SQLMesh Model: Bronze HRSA Shortage Areas
-- Transforms raw HRSA Health Professional Shortage Area data to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_bronze.hrsa_shortage_areas,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (hpsa_id)),
        unique_values(columns := (hpsa_id))
    ),
    grain hpsa_id
);

SELECT
    gen_random_uuid() AS id,

    -- HPSA identifiers
    response_body->>'hpsa_id' AS hpsa_id,
    response_body->>'designation_type' AS designation_type,
    response_body->>'state' AS state,
    response_body->>'county' AS county,
    response_body->>'discipline' AS discipline,
    (response_body->>'score')::INTEGER AS score,
    response_body->>'status' AS status,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'hrsa' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.hrsa_shortage_areas
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'hpsa_id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
