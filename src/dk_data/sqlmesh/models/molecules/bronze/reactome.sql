-- SQLMesh Model: Bronze Reactome Pathways
-- Transforms raw Reactome ContentService API responses to Bronze typed columns.
-- API: https://reactome.org/ContentService
-- Response shapes:
--   search/query:   {"results": [{stId, name, exactType, species, score}]}
--   data/query/ID:  flat object {stId, dbId, displayName, name:[], className, species:[]}

MODEL (
    name mol_bronze.reactome,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@monthly',
    audits (
        not_null(columns := (stable_id))
    ),
    grain stable_id
);

-- Search results: {"results": [{stId, name, exactType, species, score}]}
WITH from_search AS (
    SELECT
        r.id              AS raw_source_id,
        r.request_timestamp,
        item.value        AS rec
    FROM mol_raw.reactome r,
         LATERAL jsonb_array_elements(r.response_body->'results') AS item(value)
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.response_body ? 'results'
      AND r.request_timestamp BETWEEN @start_dt AND @end_dt
),

-- Individual pathway detail: flat object at root with stId
from_detail AS (
    SELECT
        r.id              AS raw_source_id,
        r.request_timestamp,
        r.response_body   AS rec
    FROM mol_raw.reactome r
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND NOT (r.response_body ? 'results')
      AND r.response_body ? 'stId'
      AND r.request_timestamp BETWEEN @start_dt AND @end_dt
),

combined AS (
    SELECT * FROM from_search
    UNION ALL
    SELECT * FROM from_detail
)

SELECT DISTINCT ON (COALESCE(rec->>'stId', rec->>'stable_id'))
    gen_random_uuid()                                                   AS id,

    COALESCE(rec->>'stId', rec->>'stable_id')                          AS stable_id,
    (rec->>'dbId')::BIGINT                                             AS db_id,

    -- Name: search gives plain string, detail gives array
    COALESCE(
        rec->>'name',
        rec->'name'->>0,
        rec->>'displayName'
    )                                                                  AS pathway_name,

    rec->>'exactType'                                                  AS entity_type,
    rec->>'className'                                                  AS class_name,

    -- Species: search gives plain string, detail gives array of objects
    COALESCE(
        rec->>'species',
        rec->'species'->0->>'displayName'
    )                                                                  AS species,

    (rec->>'score')::NUMERIC                                           AS relevance_score,

    -- Raw source tracking
    rec                                                                AS raw_json,
    raw_source_id,
    'reactome'                                                         AS source,
    request_timestamp,
    request_timestamp                                                  AS source_updated_at,
    FALSE                                                              AS processed_to_silver,
    NOW()                                                              AS created_at

FROM combined
WHERE COALESCE(rec->>'stId', rec->>'stable_id') IS NOT NULL
ORDER BY COALESCE(rec->>'stId', rec->>'stable_id'), request_timestamp DESC NULLS LAST;
