-- SQLMesh Model: Bronze WebSearch Results
-- Transforms raw web/news search API responses into typed bronze layer.
-- Response body: {"articles": [...]} or {"results": [...]} or {"organic_results": [...]}
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.websearch_results,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 1000
    ),
    cron '@daily',
    audits (
        not_null(columns := (search_query, result_url))
    )
);

WITH unnested AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        COALESCE(r.request_params->>'q', r.request_params->>'query', '') AS search_query,
        result,
        row_number() OVER (PARTITION BY r.id ORDER BY ordinality) AS result_rank
    FROM mol_raw.websearch r,
         jsonb_array_elements(
             COALESCE(
                 r.response_body->'articles',
                 r.response_body->'results',
                 r.response_body->'organic_results',
                 '[]'::JSONB
             )
         ) WITH ORDINALITY AS t(result, ordinality)
    WHERE r.response_status = 200
      AND r.response_body IS NOT NULL
)

SELECT
    gen_random_uuid()   AS id,
    raw_id,
    search_query,

    -- Search engine detected from source field
    CASE
        WHEN result->'source'->>'name' IS NOT NULL
            THEN result->'source'->>'name'
        WHEN result->>'source' IS NOT NULL
            THEN result->>'source'
        ELSE 'web'
    END AS search_engine,

    -- Type heuristic
    CASE
        WHEN search_query ILIKE '%news%'
          OR result->>'publishedAt' IS NOT NULL
            THEN 'news'
        ELSE 'general'
    END AS search_type,

    COALESCE(result->>'url', result->>'link') AS result_url,
    result->>'title'                          AS result_title,
    COALESCE(result->>'description', result->>'snippet') AS result_snippet,
    result_rank::INTEGER                      AS result_rank,

    -- Domain extracted from URL
    CASE
        WHEN COALESCE(result->>'url', result->>'link') LIKE '%/%'
            THEN split_part(split_part(COALESCE(result->>'url', result->>'link'), '/', 3), '?', 1)
        ELSE COALESCE(result->>'url', result->>'link')
    END AS result_domain,

    -- Publication date — try multiple field names, truncate to date
    CASE
        WHEN result->>'publishedAt' IS NOT NULL
            THEN LEFT(result->>'publishedAt', 10)::DATE
        WHEN result->>'date' IS NOT NULL
            THEN LEFT(result->>'date', 10)::DATE
        WHEN result->>'publication_date' IS NOT NULL
            THEN LEFT(result->>'publication_date', 10)::DATE
        ELSE NULL
    END AS publication_date,

    result->'authors'  AS authors,

    CASE
        WHEN jsonb_typeof(result->'source') = 'object'
            THEN result->'source'->>'name'
        WHEN result->>'source' IS NOT NULL
            THEN result->>'source'
        ELSE NULL
    END AS source_name,

    (COALESCE(result->>'score', result->>'relevance'))::NUMERIC AS relevance_score,

    FALSE               AS processed_to_silver,
    request_timestamp,
    request_timestamp   AS ingested_at,
    'websearch'         AS source,
    request_timestamp   AS source_updated_at

FROM unnested
WHERE COALESCE(result->>'url', result->>'link') IS NOT NULL
