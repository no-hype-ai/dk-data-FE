-- SQLMesh Model: Bronze PubMed Publications
-- Transforms flat raw.pubmed typed columns to Bronze canonical schema
-- raw.pubmed is populated by the PubMedFetcher + load_pubmed_data() loader
-- (not a generic API response table — columns are already typed)
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name bronze.pubmed,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key pmid
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

    -- Publication identifiers (flat typed columns from raw.pubmed)
    r.pmid::TEXT                         AS pmid,
    r.doi::TEXT                          AS doi,
    r.title::TEXT                        AS title,
    r.abstract::TEXT                     AS abstract,

    -- Authors stored as JSONB by the loader (list of dicts with last_name, fore_name, etc.)
    r.authors::JSONB                     AS authors,

    -- Journal info
    r.journal::TEXT                      AS journal,
    r.publication_date::DATE             AS publication_date,

    -- Classification
    r.mesh_terms::TEXT[]                 AS mesh_terms,
    r.publication_types::TEXT[]          AS publication_types,
    r.keywords::TEXT[]                   AS keywords,

    -- Source tracking
    'pubmed'                             AS source,
    r._loaded_at                         AS source_updated_at,
    FALSE                                AS processed_to_silver,
    NOW()                                AS created_at

FROM raw.pubmed r
WHERE
    r.pmid IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;
