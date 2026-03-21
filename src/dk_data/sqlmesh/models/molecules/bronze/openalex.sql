-- SQLMesh Model: Bronze OpenAlex
-- Transforms Raw OpenAlex Works search responses to Bronze typed columns
-- Part of: 012-dk-data-platform
--
-- OpenAlex search returns { results: [ { id, display_name, abstract_inverted_index, ... } ] }
-- Each result is unnested into a separate bronze row.

MODEL (
    name mol_bronze.openalex,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@weekly',
    audits (
        not_null(columns := (openalex_id))
    ),
    grain openalex_id
);

SELECT
    gen_random_uuid() AS id,

    -- OpenAlex Identifiers
    w->>'id' AS openalex_id,
    w->>'doi' AS doi,
    w->'ids'->>'pmid' AS pmid,
    w->'ids'->>'pmcid' AS pmcid,
    w->'ids'->>'mag' AS mag_id,

    -- Title and Abstract (keep inverted index as JSONB for silver reconstruction)
    w->>'display_name' AS title,
    (w->'abstract_inverted_index')::JSONB AS abstract_inverted_index,

    -- Publication Info
    w->>'type' AS work_type,
    w->>'language' AS language,
    (w->>'publication_year')::INTEGER AS publication_year,
    CASE WHEN w->>'publication_date' ~ '^\d{4}-\d{2}-\d{2}$'
         THEN (w->>'publication_date')::DATE ELSE NULL END AS publication_date,
    w->'primary_location'->'source'->>'display_name' AS journal_name,
    w->'primary_location'->'source'->>'issn_l' AS journal_issn,
    w->'primary_location'->>'pdf_url' AS pdf_url,
    (w->'primary_location'->>'is_oa')::BOOLEAN AS is_open_access,

    -- Bibliographic
    w->'biblio'->>'volume' AS volume,
    w->'biblio'->>'issue' AS issue,
    w->'biblio'->>'first_page' AS first_page,
    w->'biblio'->>'last_page' AS last_page,

    -- Authors
    w->'authorships' AS authorships,
    (SELECT jsonb_agg(a->'author'->>'display_name')
     FROM jsonb_array_elements(w->'authorships') AS a) AS author_names,

    -- Concepts and Topics
    w->'concepts' AS concepts,
    w->'topics' AS topics,
    w->'keywords' AS keywords,
    w->'mesh' AS mesh_terms,

    -- Metrics
    (w->>'cited_by_count')::INTEGER AS cited_by_count,
    w->'counts_by_year' AS citation_counts_by_year,

    -- Grants
    w->'grants' AS grants,

    -- References
    w->'referenced_works' AS referenced_works,
    w->'related_works' AS related_works,

    -- Access
    w->'open_access' AS open_access_info,
    w->'best_oa_location' AS best_oa_location,

    -- Indexed Status
    (w->>'is_retracted')::BOOLEAN AS is_retracted,
    (w->>'is_paratext')::BOOLEAN AS is_paratext,

    -- Raw source tracking
    w AS raw_json,
    r.id AS raw_source_id,
    'openalex' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.openalex r,
     jsonb_array_elements(response_body->'results') AS w
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->'results' IS NOT NULL
    AND jsonb_array_length(response_body->'results') > 0
    AND w->>'id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
