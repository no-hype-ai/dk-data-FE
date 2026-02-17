-- SQLMesh Model: Silver Publications
-- Normalized publication data from OpenAlex
-- Part of: 012-dk-data-platform

MODEL (
    name silver.publications,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key doi
    ),
    cron '@weekly',
    audits (
        not_null(columns := (title))
    ),
    grain doi
);

WITH openalex_pubs AS (
    SELECT
        openalex_id,
        doi,
        pmid,
        pmcid,
        title,
        -- Reconstruct abstract from inverted index (simplified)
        NULL::TEXT AS abstract,  -- Would need complex reconstruction
        work_type AS publication_type,
        language,
        publication_year,
        publication_date,
        journal_name,
        journal_issn,
        volume,
        issue,
        first_page,
        last_page,
        author_names,
        authorships,
        concepts,
        keywords,
        mesh_terms,
        cited_by_count,
        citation_counts_by_year,
        is_open_access,
        pdf_url,
        is_retracted,
        grants,
        source,
        source_updated_at,
        created_at
    FROM bronze.openalex
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- Extract first author
enriched AS (
    SELECT
        *,
        -- First author info
        authorships->0->'author'->>'display_name' AS first_author_name,
        authorships->0->'author'->>'id' AS first_author_id,
        authorships->0->'institutions'->0->>'display_name' AS first_author_institution,
        -- Author count
        jsonb_array_length(authorships) AS author_count,
        -- Top concepts
        (SELECT jsonb_agg(c->>'display_name')
         FROM jsonb_array_elements(concepts) AS c
         WHERE (c->>'score')::NUMERIC > 0.5
         LIMIT 5) AS top_concepts
    FROM openalex_pubs
)

SELECT
    gen_random_uuid() AS id,
    openalex_id,
    doi,
    pmid::BIGINT AS pmid,
    pmcid,
    title,
    abstract,
    publication_type,
    language,
    publication_year,
    publication_date,
    journal_name,
    journal_issn,
    volume,
    issue,
    first_page,
    last_page,
    first_author_name,
    first_author_institution,
    author_count,
    author_names,
    top_concepts AS concepts,
    mesh_terms,
    cited_by_count,
    is_open_access,
    pdf_url,
    is_retracted,
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM enriched;


-- NOTE: Bronze processed_to_silver flag updates are handled outside SQLMesh.
-- Silver models use INCREMENTAL_BY_UNIQUE_KEY with INCREMENTAL_BY_UNIQUE_KEY (default: update all columns on match),
-- so reprocessing is idempotent.
