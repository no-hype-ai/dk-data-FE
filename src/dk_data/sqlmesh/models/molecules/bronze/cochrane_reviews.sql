-- SQLMesh Model: Bronze Cochrane Reviews
-- Transforms raw Cochrane Library API responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_bronze.cochrane_reviews,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (review_id)),
        unique_values(columns := (review_id))
    ),
    grain review_id
);

SELECT
    gen_random_uuid() AS id,

    -- Review identifiers
    response_body->>'id' AS review_id,
    response_body->>'title' AS title,
    response_body->'authors' AS authors,
    response_body->>'abstract' AS abstract,
    response_body->>'pub_date' AS pub_date,
    response_body->>'doi' AS doi,
    response_body->>'review_type' AS review_type,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'cochrane_reviews' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.cochrane_reviews
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
