-- SQLMesh Model: Bronze ClinicalTrials.gov Indication Statistics
-- Extracts totalCount and query condition from CT.gov v2 API responses
-- Part of: 003-molecule-assessment-dashboard

MODEL (
    name mol_bronze.ct_gov_indication_stats,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@monthly',
    audits (
        not_null(columns := (condition_query))
    ),
    grain (condition_query, request_timestamp)
);

SELECT
    gen_random_uuid() AS id,

    -- CT.gov stats
    drug_name AS condition_query,
    (response_body->>'totalCount')::INTEGER AS total_count,

    -- Source tracking
    response_body AS raw_json,
    r.id AS raw_source_id,
    'ct_gov_indication_stats' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.ct_gov_indication_stats r
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'totalCount' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
