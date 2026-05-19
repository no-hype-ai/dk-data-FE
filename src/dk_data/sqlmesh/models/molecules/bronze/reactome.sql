-- SQLMesh Model: Bronze Reactome Pathways
-- Transforms raw Reactome ContentService API responses to Bronze typed columns.
-- API: https://reactome.org/ContentService
-- Response shapes:
--   search/query:   {"results": [{stId, name, exactType, species, score}]}
--   data/query/ID:  flat object {stId, dbId, displayName, name:[], className, species:[]}

MODEL (
    name mol_bronze.reactome,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key stable_id
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
        r.ingested_at,
        item.value        AS rec
    FROM mol_raw.reactome r,
         LATERAL jsonb_array_elements(r.response_body->'results') AS item(value)
    WHERE r.response_body ? 'results'
),

-- Individual pathway detail: flat object at root with stId
from_detail AS (
    SELECT
        r.id              AS raw_source_id,
        r.ingested_at,
        r.response_body   AS rec
    FROM mol_raw.reactome r
    WHERE NOT (r.response_body ? 'results')
      AND r.response_body ? 'stId'
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

    -- Name: both search and detail responses return an array; extract first element.
    -- Try array index first to avoid returning the raw JSON array string.
    COALESCE(
        rec->'name'->>0,
        rec->>'displayName',
        rec->>'name'
    )                                                                  AS pathway_name,

    rec->>'exactType'                                                  AS entity_type,
    rec->>'className'                                                  AS class_name,

    -- Species: detail response has an array of objects; extract displayName from first element.
    -- Try array-of-objects form first to avoid returning the raw JSON array string.
    COALESCE(
        rec->'species'->0->>'displayName',
        rec->>'species'
    )                                                                  AS species,

    (rec->>'score')::NUMERIC                                           AS relevance_score,

    -- Raw source tracking
    rec                                                                AS raw_json,
    raw_source_id,
    'reactome'                                                         AS source,
    ingested_at,
    ingested_at                                                    AS source_updated_at,
    FALSE                                                              AS processed_to_silver,
    NOW()                                                              AS created_at

FROM combined
WHERE COALESCE(rec->>'stId', rec->>'stable_id') IS NOT NULL
ORDER BY COALESCE(rec->>'stId', rec->>'stable_id'), ingested_at DESC NULLS LAST;
