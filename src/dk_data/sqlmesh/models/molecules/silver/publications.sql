-- SQLMesh Model: Silver Publications
-- Zero data loss from Bronze. Column names match bronze (API-derived snake_case).
-- Primary source: openalex. Secondary: pubmed, cochrane, journal_rss (NULL-padded).
-- Adds: abstract (reconstructed from abstract_inverted_index), first_author_name,
--        first_author_institution, author_count, top_concepts, molecule_id linkage.

MODEL (
    name mol_silver.publications,
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
        mag_id,
        title,
        -- Reconstruct abstract from inverted index
        (SELECT string_agg(word, ' ' ORDER BY pos)
         FROM (
           SELECT kv.key AS word, p.pos::INT AS pos
           FROM jsonb_each(abstract_inverted_index) AS kv,
                LATERAL jsonb_array_elements_text(kv.value) AS p(pos)
         ) sub
        ) AS abstract,
        work_type,
        language,
        publication_year,
        publication_date,
        journal_name,
        journal_issn,
        pdf_url,
        is_open_access,
        volume,
        issue,
        first_page,
        last_page,
        authorships,
        author_names,
        concepts,
        topics,
        keywords,
        mesh_terms,
        cited_by_count,
        citation_counts_by_year,
        grants,
        referenced_works,
        related_works,
        open_access_info,
        best_oa_location,
        is_retracted,
        is_paratext,
        source,
        source_updated_at,
        created_at
    FROM mol_bronze.openalex
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- Secondary source: PubMed publications
pubmed_pubs AS (
    SELECT
        'pubmed:' || pmid AS openalex_id,
        doi,
        pmid,
        NULL::TEXT AS pmcid,
        NULL::TEXT AS mag_id,
        title,
        abstract,
        'journal-article' AS work_type,
        NULL::TEXT AS language,
        EXTRACT(YEAR FROM pub_date::DATE)::INTEGER AS publication_year,
        pub_date AS publication_date,
        journal AS journal_name,
        NULL::TEXT AS journal_issn,
        NULL::TEXT AS pdf_url,
        NULL::BOOLEAN AS is_open_access,
        NULL::TEXT AS volume,
        NULL::TEXT AS issue,
        NULL::TEXT AS first_page,
        NULL::TEXT AS last_page,
        authors AS authorships,
        NULL::JSONB AS author_names,
        NULL::JSONB AS concepts,
        NULL::JSONB AS topics,
        NULL::JSONB AS keywords,
        mesh_terms,
        NULL::INTEGER AS cited_by_count,
        NULL::JSONB AS citation_counts_by_year,
        NULL::JSONB AS grants,
        NULL::JSONB AS referenced_works,
        NULL::JSONB AS related_works,
        NULL::JSONB AS open_access_info,
        NULL::JSONB AS best_oa_location,
        NULL::BOOLEAN AS is_retracted,
        NULL::BOOLEAN AS is_paratext,
        source,
        source_updated_at,
        created_at
    FROM mol_bronze.pubmed
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- Secondary source: Cochrane systematic reviews
cochrane_pubs AS (
    SELECT
        'cochrane:' || review_id AS openalex_id,
        doi,
        NULL::TEXT AS pmid,
        NULL::TEXT AS pmcid,
        NULL::TEXT AS mag_id,
        title,
        abstract,
        review_type AS work_type,
        NULL::TEXT AS language,
        EXTRACT(YEAR FROM pub_date::DATE)::INTEGER AS publication_year,
        pub_date AS publication_date,
        'Cochrane Database of Systematic Reviews' AS journal_name,
        NULL::TEXT AS journal_issn,
        NULL::TEXT AS pdf_url,
        NULL::BOOLEAN AS is_open_access,
        NULL::TEXT AS volume,
        NULL::TEXT AS issue,
        NULL::TEXT AS first_page,
        NULL::TEXT AS last_page,
        authors AS authorships,
        NULL::JSONB AS author_names,
        NULL::JSONB AS concepts,
        NULL::JSONB AS topics,
        NULL::JSONB AS keywords,
        NULL::JSONB AS mesh_terms,
        NULL::INTEGER AS cited_by_count,
        NULL::JSONB AS citation_counts_by_year,
        NULL::JSONB AS grants,
        NULL::JSONB AS referenced_works,
        NULL::JSONB AS related_works,
        NULL::JSONB AS open_access_info,
        NULL::JSONB AS best_oa_location,
        NULL::BOOLEAN AS is_retracted,
        NULL::BOOLEAN AS is_paratext,
        source,
        source_updated_at,
        created_at
    FROM mol_bronze.cochrane_reviews
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- Secondary source: Journal RSS feed entries
journal_rss_pubs AS (
    SELECT
        'rss:' || entry_id AS openalex_id,
        doi,
        NULL::TEXT AS pmid,
        NULL::TEXT AS pmcid,
        NULL::TEXT AS mag_id,
        title,
        summary AS abstract,
        'journal-article' AS work_type,
        NULL::TEXT AS language,
        EXTRACT(YEAR FROM pub_date::DATE)::INTEGER AS publication_year,
        pub_date AS publication_date,
        journal_name,
        NULL::TEXT AS journal_issn,
        NULL::TEXT AS pdf_url,
        NULL::BOOLEAN AS is_open_access,
        NULL::TEXT AS volume,
        NULL::TEXT AS issue,
        NULL::TEXT AS first_page,
        NULL::TEXT AS last_page,
        authors AS authorships,
        NULL::JSONB AS author_names,
        NULL::JSONB AS concepts,
        NULL::JSONB AS topics,
        NULL::JSONB AS keywords,
        NULL::JSONB AS mesh_terms,
        NULL::INTEGER AS cited_by_count,
        NULL::JSONB AS citation_counts_by_year,
        NULL::JSONB AS grants,
        NULL::JSONB AS referenced_works,
        NULL::JSONB AS related_works,
        NULL::JSONB AS open_access_info,
        NULL::JSONB AS best_oa_location,
        NULL::BOOLEAN AS is_retracted,
        NULL::BOOLEAN AS is_paratext,
        source,
        source_updated_at,
        created_at
    FROM mol_bronze.journal_rss
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

-- Derive first_author fields and top concepts
enriched AS (
    SELECT
        *,
        -- First author (derived from authorships JSONB)
        authorships->0->'author'->>'display_name' AS first_author_name,
        authorships->0->'author'->>'id' AS first_author_id,
        authorships->0->'institutions'->0->>'display_name' AS first_author_institution,
        -- Author count
        COALESCE(jsonb_array_length(authorships), 0) AS author_count,
        -- Top concepts (score > 0.5, up to 5)
        (SELECT jsonb_agg(c->>'display_name')
         FROM jsonb_array_elements(COALESCE(concepts, '[]'::JSONB)) AS c
         WHERE (c->>'score')::NUMERIC > 0.5
         LIMIT 5) AS top_concepts
    FROM combined_pubs
)

SELECT DISTINCT ON (e.doi)
    gen_random_uuid() AS id,
    m.molecule_id,

    -- Identifiers (bronze names preserved)
    e.openalex_id,
    e.doi,
    e.pmid,
    e.pmcid,
    e.mag_id,

    -- Content
    e.title,
    e.abstract,

    -- Publication metadata (bronze names preserved)
    e.work_type,
    e.language,
    e.publication_year,
    e.publication_date,
    e.journal_name,
    e.journal_issn,
    e.pdf_url,
    e.is_open_access,

    -- Bibliographic (bronze names preserved)
    e.volume,
    e.issue,
    e.first_page,
    e.last_page,

    -- Authors (bronze names preserved + derived)
    e.authorships,
    e.author_names,
    e.first_author_name,
    e.first_author_id,
    e.first_author_institution,
    e.author_count,

    -- Concepts and topics (bronze names preserved)
    e.top_concepts AS concepts,
    e.topics,
    e.keywords,
    e.mesh_terms,

    -- Metrics (bronze names preserved)
    e.cited_by_count,
    e.citation_counts_by_year,

    -- Grants (bronze name preserved)
    e.grants,

    -- References (bronze names preserved)
    e.referenced_works,
    e.related_works,

    -- Access (bronze names preserved)
    e.open_access_info,
    e.best_oa_location,

    -- Status flags (bronze names preserved)
    e.is_retracted,
    e.is_paratext,

    -- Source tracking
    e.source,
    e.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM enriched e
LEFT JOIN mol_silver.molecules m ON (
    LOWER(e.title) LIKE '%' || LOWER(m.canonical_name) || '%'
    AND LENGTH(m.canonical_name) > 4
)
ORDER BY e.doi,
    CASE e.source
        WHEN 'openalex' THEN 1
        WHEN 'pubmed' THEN 2
        WHEN 'cochrane_reviews' THEN 3
        WHEN 'journal_rss' THEN 4
    END;
