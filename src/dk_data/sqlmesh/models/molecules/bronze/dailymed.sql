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

SELECT
    gen_random_uuid() AS id,

    -- SPL identifiers (entity linking key)
    spl->>'setid' AS setid,
    (spl->>'spl_version')::INTEGER AS spl_version,
    spl->>'published_date' AS published_date,
    spl->>'title' AS title,

    -- Parsed fields from normalized title
    spl->>'brand_name' AS brand_name,
    spl->>'generic_name' AS generic_name,
    spl->>'manufacturer' AS manufacturer,

    -- Entity linking metadata
    spl->>'entity_link_key' AS entity_link_key,
    spl->>'entity_link_type' AS entity_link_type,

    -- Source tracking
    drug_name AS query_name,
    response_body AS raw_json,
    r.id AS raw_source_id,
    'dailymed' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.dailymed r,
     jsonb_array_elements(response_body->'data') AS spl
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->'data' IS NOT NULL
    AND jsonb_array_length(response_body->'data') > 0
    AND spl->>'setid' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
