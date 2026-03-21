-- SQLMesh Model: Bronze PubMed Publications
-- Transforms raw PubMed eutils API responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name bronze.pubmed,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (pmid)),
        unique_values(columns := (pmid))
    ),
    grain pmid
);

SELECT
    gen_random_uuid() AS id,

    -- Publication identifiers
    response_body->>'uid' AS pmid,
    response_body->>'title' AS title,
    response_body->>'abstract' AS abstract,

    -- Authors
    response_body->'authors' AS authors,

    -- Journal info
    response_body->>'fulljournalname' AS journal,
    response_body->>'sortpubdate' AS pub_date,

    -- Classification
    response_body->'meshterms' AS mesh_terms,
    response_body->>'elocationid' AS doi,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'pubmed' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.pubmed
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'uid' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
