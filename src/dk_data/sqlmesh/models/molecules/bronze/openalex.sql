-- SQLMesh Model: Bronze OpenAlex
-- Transforms Raw OpenAlex Works responses to Bronze typed columns
-- Part of: 012-dk-data-platform

MODEL (
    name bronze.openalex,
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
    response_body->>'id' AS openalex_id,
    response_body->>'doi' AS doi,
    response_body->'ids'->>'pmid' AS pmid,
    response_body->'ids'->>'pmcid' AS pmcid,
    response_body->'ids'->>'mag' AS mag_id,

    -- Title and Abstract
    response_body->>'display_name' AS title,
    response_body->'abstract_inverted_index' AS abstract_inverted_index,

    -- Publication Info
    response_body->>'type' AS work_type,
    response_body->>'language' AS language,
    (response_body->>'publication_year')::INTEGER AS publication_year,
    (response_body->>'publication_date')::DATE AS publication_date,
    response_body->'primary_location'->'source'->>'display_name' AS journal_name,
    response_body->'primary_location'->'source'->>'issn_l' AS journal_issn,
    response_body->'primary_location'->>'pdf_url' AS pdf_url,
    (response_body->'primary_location'->>'is_oa')::BOOLEAN AS is_open_access,

    -- Bibliographic
    response_body->'biblio'->>'volume' AS volume,
    response_body->'biblio'->>'issue' AS issue,
    response_body->'biblio'->>'first_page' AS first_page,
    response_body->'biblio'->>'last_page' AS last_page,

    -- Authors
    response_body->'authorships' AS authorships,
    (SELECT jsonb_agg(a->'author'->>'display_name')
     FROM jsonb_array_elements(response_body->'authorships') AS a) AS author_names,

    -- Concepts and Topics
    response_body->'concepts' AS concepts,
    response_body->'topics' AS topics,
    response_body->'keywords' AS keywords,
    response_body->'mesh' AS mesh_terms,

    -- Metrics
    (response_body->>'cited_by_count')::INTEGER AS cited_by_count,
    (response_body->>'cited_by_percentile_year'->>'min')::NUMERIC AS cited_by_percentile,
    (response_body->'counts_by_year') AS citation_counts_by_year,

    -- Grants
    response_body->'grants' AS grants,

    -- References
    response_body->'referenced_works' AS referenced_works,
    response_body->'related_works' AS related_works,

    -- Sustainability
    response_body->'sustainable_development_goals' AS sustainable_development_goals,

    -- Access
    response_body->'open_access' AS open_access_info,
    response_body->'best_oa_location' AS best_oa_location,

    -- Indexed Status
    (response_body->>'is_retracted')::BOOLEAN AS is_retracted,
    (response_body->>'is_paratext')::BOOLEAN AS is_paratext,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'openalex' AS source,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM raw.openalex
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
