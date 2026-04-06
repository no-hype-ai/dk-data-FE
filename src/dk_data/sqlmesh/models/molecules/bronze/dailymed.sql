-- SQLMesh Model: Bronze DailyMed SPL
-- Extracts SPL metadata from DailyMed search responses
-- Part of: 003-molecule-assessment-dashboard
--
-- Entity linking: setid (UUID) maps to mol_silver.drug_labels.spl_set_id

MODEL (
    name mol_bronze.dailymed,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@monthly',
    audits (
        not_null(columns := (setid))
    ),
    grain setid
);

-- Each mol_raw.dailymed row is a single SPL record stored directly (not wrapped in a "data" array).
-- The DailyMed API returns {"data": [...]} pages, but the ingestion layer stores individual
-- SPL records extracted from those pages — one record per row in mol_raw.
SELECT
    gen_random_uuid() AS id,

    -- SPL identifiers (entity linking key)
    response_body->>'setid' AS setid,
    (response_body->>'spl_version')::INTEGER AS spl_version,
    response_body->>'published_date' AS published_date,
    response_body->>'title' AS title,

    -- Parsed fields from normalized title
    response_body->>'brand_name' AS brand_name,
    response_body->>'generic_name' AS generic_name,
    response_body->>'manufacturer' AS manufacturer,

    -- Entity linking metadata
    response_body->>'entity_link_key' AS entity_link_key,
    response_body->>'entity_link_type' AS entity_link_type,

    -- Source tracking
    request_params->>'drug_name' AS query_name,
    response_body AS raw_json,
    r.id AS raw_source_id,
    'dailymed' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.dailymed r
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'setid' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
