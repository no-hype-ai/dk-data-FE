-- SQLMesh Model: Bronze Medical News
-- Transforms raw medical news aggregator responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_bronze.medical_news,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (article_id)),
        unique_values(columns := (article_id))
    ),
    grain article_id
);

SELECT
    gen_random_uuid() AS id,

    -- Article identifiers
    COALESCE(
        response_body->>'id',
        response_body->>'link'
    ) AS article_id,
    response_body->>'title' AS title,
    response_body->>'link' AS link,
    response_body->>'pub_date' AS pub_date,
    response_body->>'source_name' AS source_name,
    response_body->>'summary' AS summary,
    response_body->'drug_mentions' AS drug_mentions,
    response_body->>'sentiment' AS sentiment,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'medical_news' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.medical_news
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'title' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
