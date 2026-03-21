-- SQLMesh Model: Bronze Journal RSS Feeds
-- Transforms raw journal RSS feed entries to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name bronze.journal_rss,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (entry_id)),
        unique_values(columns := (entry_id))
    ),
    grain entry_id
);

SELECT
    gen_random_uuid() AS id,

    -- Entry identifiers
    COALESCE(
        response_body->>'id',
        response_body->>'link'
    ) AS entry_id,
    response_body->>'title' AS title,
    response_body->>'link' AS link,
    response_body->>'published' AS pub_date,
    response_body->>'journal_name' AS journal_name,
    response_body->>'summary' AS summary,
    response_body->'authors' AS authors,
    response_body->>'doi' AS doi,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'journal_rss' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.journal_rss
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'title' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
