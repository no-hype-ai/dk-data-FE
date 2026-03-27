-- SQLMesh Model: Bronze OpenAlex
-- Transforms flat raw.openalex_ci typed columns to Bronze canonical schema
-- raw.openalex_ci is populated by OpenAlexCIFetcher + load_openalex_ci_data()
-- Columns are typed at load time; JSONB fields (concepts, authorships, etc.)
-- are stored as JSONB blobs. The loader normalises the OpenAlex API response
-- into this flat schema — no JSON path drilling needed here.
-- Part of: 012-dk-data-platform

MODEL (
    name bronze.openalex,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key openalex_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (openalex_id))
    ),
    grain openalex_id
);

SELECT
    gen_random_uuid()                                                      AS id,

    -- OpenAlex Identifiers
    r.work_id::TEXT                                                        AS openalex_id,
    r.doi::TEXT                                                            AS doi,

    -- PMID is not stored directly in raw.openalex_ci; derive from authorships
    -- if available, otherwise NULL (PMID linkage done at silver layer via doi)
    NULL::TEXT                                                             AS pmid,
    NULL::TEXT                                                             AS pmcid,
    NULL::TEXT                                                             AS mag_id,

    -- Title and Abstract (abstract reconstructed by fetcher from inverted index)
    r.title::TEXT                                                          AS title,
    r.abstract::TEXT                                                       AS abstract,
    NULL::JSONB                                                            AS abstract_inverted_index,

    -- Publication Info (publication_year derived from publication_date)
    NULL::TEXT                                                             AS work_type,
    NULL::TEXT                                                             AS language,
    EXTRACT(YEAR FROM r.publication_date)::INTEGER                        AS publication_year,
    r.publication_date::DATE                                               AS publication_date,

    -- Journal info from primary_location JSONB
    -- OpenAlex primary_location structure: {source: {display_name, issn_l, ...}, pdf_url, is_oa, ...}
    (r.primary_location->'source'->>'display_name')::TEXT                AS journal_name,
    (r.primary_location->'source'->>'issn_l')::TEXT                     AS journal_issn,
    (r.primary_location->>'pdf_url')::TEXT                               AS pdf_url,
    -- open_access structure: {is_oa: bool, oa_status: ..., oa_url: ...}
    (r.open_access->>'is_oa')::BOOLEAN                                   AS is_open_access,

    -- Bibliographic (not stored at raw layer)
    NULL::TEXT                                                             AS volume,
    NULL::TEXT                                                             AS issue,
    NULL::TEXT                                                             AS first_page,
    NULL::TEXT                                                             AS last_page,

    -- Authors
    r.authorships::JSONB                                                   AS authorships,
    (SELECT jsonb_agg(a->'author'->>'display_name')
     FROM jsonb_array_elements(COALESCE(r.authorships, '[]'::JSONB)) AS a) AS author_names,

    -- Concepts and Topics
    r.concepts::JSONB                                                      AS concepts,
    NULL::JSONB                                                            AS topics,
    NULL::JSONB                                                            AS keywords,
    NULL::JSONB                                                            AS mesh_terms,

    -- Metrics
    r.cited_by_count::INTEGER                                              AS cited_by_count,
    NULL::NUMERIC                                                          AS cited_by_percentile,
    NULL::JSONB                                                            AS citation_counts_by_year,

    -- Grants (not stored at raw layer)
    NULL::JSONB                                                            AS grants,
    NULL::JSONB                                                            AS referenced_works,
    NULL::JSONB                                                            AS related_works,
    NULL::JSONB                                                            AS sustainable_development_goals,

    -- Access
    r.open_access::JSONB                                                   AS open_access_info,
    NULL::JSONB                                                            AS best_oa_location,

    -- Indexed Status (not stored at raw layer)
    NULL::BOOLEAN                                                          AS is_retracted,
    NULL::BOOLEAN                                                          AS is_paratext,

    -- Source tracking
    'openalex'                                                             AS source,
    r._loaded_at                                                           AS source_updated_at,
    FALSE                                                                  AS processed_to_silver,
    NOW()                                                                  AS created_at

FROM raw.openalex_ci r
WHERE
    r.work_id IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;
