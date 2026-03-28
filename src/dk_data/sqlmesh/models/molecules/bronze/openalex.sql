-- SQLMesh Model: Bronze OpenAlex
-- Transforms flat mol_raw.openalex_ci typed columns to Bronze canonical schema
-- mol_raw.openalex_ci is populated by OpenAlexCIFetcher + load_openalex_ci_data()
-- Columns are typed at load time; JSONB fields (concepts, authorships, etc.)
-- are stored as JSONB blobs. The loader normalises the OpenAlex API response
-- into this flat schema — no JSON path drilling needed here.
-- Extended columns (pmid, pmcid, mag_id, work_type, language, biblio fields,
-- topics, keywords, mesh_terms, metrics, grants, related works, SDGs, etc.)
-- were added in migration 112 and are now populated by the updated fetcher.
-- Part of: 012-dk-data-platform

MODEL (
    name mol_bronze.openalex,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at
    ),
    cron '@weekly',
    audits (
        not_null(columns := (openalex_id))
    )
);

SELECT
    gen_random_uuid()                                                      AS id,

    -- OpenAlex Identifiers
    r.work_id::TEXT                                                        AS openalex_id,
    r.doi::TEXT                                                            AS doi,

    -- Cross-reference IDs (stored in mol_raw.openalex_ci since migration 112)
    r.pmid::TEXT                                                           AS pmid,
    r.pmcid::TEXT                                                          AS pmcid,
    r.mag_id::TEXT                                                         AS mag_id,

    -- Title and Abstract (abstract reconstructed by fetcher from inverted index)
    r.title::TEXT                                                          AS title,
    r.abstract::TEXT                                                       AS abstract,
    -- abstract_inverted_index: OpenAlex API returns this only on dedicated /works/{id} calls,
    -- not in the search/filter endpoint — genuinely unavailable at bulk ingest
    NULL::JSONB                                                            AS abstract_inverted_index,

    -- Publication Info (stored in mol_raw.openalex_ci since migration 112)
    r.work_type::TEXT                                                      AS work_type,
    r.language::TEXT                                                       AS language,
    EXTRACT(YEAR FROM r.publication_date)::INTEGER                        AS publication_year,
    r.publication_date::DATE                                               AS publication_date,

    -- Journal info from primary_location JSONB
    -- OpenAlex primary_location structure: {source: {display_name, issn_l, ...}, pdf_url, is_oa, ...}
    (r.primary_location->'source'->>'display_name')::TEXT                AS journal_name,
    (r.primary_location->'source'->>'issn_l')::TEXT                     AS journal_issn,
    (r.primary_location->>'pdf_url')::TEXT                               AS pdf_url,
    -- open_access structure: {is_oa: bool, oa_status: ..., oa_url: ...}
    (r.open_access->>'is_oa')::BOOLEAN                                   AS is_open_access,

    -- Bibliographic fields (stored in mol_raw.openalex_ci since migration 112)
    r.volume::TEXT                                                         AS volume,
    r.issue::TEXT                                                          AS issue,
    r.first_page::TEXT                                                     AS first_page,
    r.last_page::TEXT                                                      AS last_page,

    -- Authors
    r.authorships::JSONB                                                   AS authorships,
    (SELECT jsonb_agg(a->'author'->>'display_name')
     FROM jsonb_array_elements(COALESCE(r.authorships, '[]'::JSONB)) AS a) AS author_names,

    -- Concepts and Topics (stored in mol_raw.openalex_ci since migration 112)
    r.concepts::JSONB                                                      AS concepts,
    r.topics::JSONB                                                        AS topics,
    r.keywords::JSONB                                                      AS keywords,
    r.mesh_terms::JSONB                                                    AS mesh_terms,

    -- Metrics (stored in mol_raw.openalex_ci since migration 112)
    r.cited_by_count::INTEGER                                              AS cited_by_count,
    r.cited_by_percentile::NUMERIC                                         AS cited_by_percentile,
    r.citation_counts_by_year::JSONB                                       AS citation_counts_by_year,

    -- Grants and related works (stored in mol_raw.openalex_ci since migration 112)
    r.grants::JSONB                                                        AS grants,
    r.referenced_works::JSONB                                              AS referenced_works,
    r.related_works::JSONB                                                 AS related_works,
    r.sustainable_development_goals::JSONB                                 AS sustainable_development_goals,

    -- Access (stored in mol_raw.openalex_ci since migration 112)
    r.open_access::JSONB                                                   AS open_access_info,
    r.best_oa_location::JSONB                                              AS best_oa_location,

    -- Indexed Status (stored in mol_raw.openalex_ci since migration 112)
    r.is_retracted::BOOLEAN                                                AS is_retracted,
    r.is_paratext::BOOLEAN                                                 AS is_paratext,

    -- Source tracking
    'openalex'                                                             AS source,
    r._loaded_at                                                           AS source_updated_at,
    FALSE                                                                  AS processed_to_silver,
    NOW()                                                                  AS created_at

FROM mol_raw.openalex_ci r
WHERE
    r.work_id IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;
