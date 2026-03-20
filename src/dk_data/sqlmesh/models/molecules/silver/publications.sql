-- SQLMesh Model: Silver Publications
-- Normalized publication data from OpenAlex, PubMed, Cochrane, and Journal RSS
-- Part of: 012-dk-data-platform (extended by 015-assessment-dashboard-integration)

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
        -- Reconstruct abstract from inverted index
        (SELECT string_agg(word, ' ' ORDER BY pos)
         FROM (
           SELECT kv.key AS word, p.pos::INT AS pos
           FROM jsonb_each(abstract_inverted_index) AS kv,
                LATERAL jsonb_array_elements_text(kv.value) AS p(pos)
         ) sub
        ) AS abstract,
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

-- Feature 015: PubMed publications
pubmed_pubs AS (
    SELECT
        'pubmed:' || pmid AS openalex_id,
        doi,
        pmid,
        NULL::TEXT AS pmcid,
        title,
        abstract,
        'journal-article' AS publication_type,
        NULL::TEXT AS language,
        EXTRACT(YEAR FROM pub_date::DATE)::INTEGER AS publication_year,
        pub_date AS publication_date,
        journal AS journal_name,
        NULL::TEXT AS journal_issn,
        NULL::TEXT AS volume,
        NULL::TEXT AS issue,
        NULL::TEXT AS first_page,
        NULL::TEXT AS last_page,
        NULL::JSONB AS author_names,
        authors AS authorships,
        NULL::JSONB AS concepts,
        NULL::JSONB AS keywords,
        mesh_terms,
        NULL::INTEGER AS cited_by_count,
        NULL::JSONB AS citation_counts_by_year,
        NULL::BOOLEAN AS is_open_access,
        NULL::TEXT AS pdf_url,
        NULL::BOOLEAN AS is_retracted,
        NULL::JSONB AS grants,
        source,
        source_updated_at,
        created_at
    FROM bronze.pubmed
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- Feature 015: Cochrane systematic reviews
cochrane_pubs AS (
    SELECT
        'cochrane:' || review_id AS openalex_id,
        doi,
        NULL::TEXT AS pmid,
        NULL::TEXT AS pmcid,
        title,
        abstract,
        review_type AS publication_type,
        NULL::TEXT AS language,
        EXTRACT(YEAR FROM pub_date::DATE)::INTEGER AS publication_year,
        pub_date AS publication_date,
        'Cochrane Database of Systematic Reviews' AS journal_name,
        NULL::TEXT AS journal_issn,
        NULL::TEXT AS volume,
        NULL::TEXT AS issue,
        NULL::TEXT AS first_page,
        NULL::TEXT AS last_page,
        NULL::JSONB AS author_names,
        authors AS authorships,
        NULL::JSONB AS concepts,
        NULL::JSONB AS keywords,
        NULL::JSONB AS mesh_terms,
        NULL::INTEGER AS cited_by_count,
        NULL::JSONB AS citation_counts_by_year,
        NULL::BOOLEAN AS is_open_access,
        NULL::TEXT AS pdf_url,
        NULL::BOOLEAN AS is_retracted,
        NULL::JSONB AS grants,
        source,
        source_updated_at,
        created_at
    FROM bronze.cochrane_reviews
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- Feature 015: Journal RSS feed entries
journal_rss_pubs AS (
    SELECT
        'rss:' || entry_id AS openalex_id,
        doi,
        NULL::TEXT AS pmid,
        NULL::TEXT AS pmcid,
        title,
        summary AS abstract,
        'journal-article' AS publication_type,
        NULL::TEXT AS language,
        EXTRACT(YEAR FROM pub_date::DATE)::INTEGER AS publication_year,
        pub_date AS publication_date,
        journal_name,
        NULL::TEXT AS journal_issn,
        NULL::TEXT AS volume,
        NULL::TEXT AS issue,
        NULL::TEXT AS first_page,
        NULL::TEXT AS last_page,
        NULL::JSONB AS author_names,
        authors AS authorships,
        NULL::JSONB AS concepts,
        NULL::JSONB AS keywords,
        NULL::JSONB AS mesh_terms,
        NULL::INTEGER AS cited_by_count,
        NULL::JSONB AS citation_counts_by_year,
        NULL::BOOLEAN AS is_open_access,
        NULL::TEXT AS pdf_url,
        NULL::BOOLEAN AS is_retracted,
        NULL::JSONB AS grants,
        source,
        source_updated_at,
        created_at
    FROM bronze.journal_rss
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- Combine all publication sources
combined_pubs AS (
    SELECT * FROM openalex_pubs
    UNION ALL
    SELECT * FROM pubmed_pubs
    UNION ALL
    SELECT * FROM cochrane_pubs
    UNION ALL
    SELECT * FROM journal_rss_pubs
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
        COALESCE(jsonb_array_length(authorships), 0) AS author_count,
        -- Top concepts
        (SELECT jsonb_agg(c->>'display_name')
         FROM jsonb_array_elements(COALESCE(concepts, '[]'::JSONB)) AS c
         WHERE (c->>'score')::NUMERIC > 0.5
         LIMIT 5) AS top_concepts
    FROM combined_pubs
)

SELECT DISTINCT ON (doi)
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
    grants,
    citation_counts_by_year,
    authorships,
    keywords,
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM enriched
ORDER BY doi,
    CASE source
        WHEN 'openalex' THEN 1
        WHEN 'pubmed' THEN 2
        WHEN 'cochrane_reviews' THEN 3
        WHEN 'journal_rss' THEN 4
    END;
