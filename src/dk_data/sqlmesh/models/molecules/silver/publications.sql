-- SQLMesh Model: Silver Publications
-- Normalized publication data from OpenAlex, PubMed, Cochrane, and Journal RSS
-- Reads from bronze.* models which themselves read from flat raw.* typed tables.
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
        abstract,
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

-- PubMed publications
-- bronze.pubmed now exposes flat columns: pmid, doi, title, abstract, journal,
-- publication_date, mesh_terms (TEXT[]), authors (JSONB), publication_types (TEXT[])
pubmed_pubs AS (
    SELECT
        'pubmed:' || pmid                                        AS openalex_id,
        doi,
        pmid,
        NULL::TEXT                                               AS pmcid,
        title,
        abstract,
        'journal-article'                                        AS publication_type,
        NULL::TEXT                                               AS language,
        EXTRACT(YEAR FROM publication_date)::INTEGER            AS publication_year,
        publication_date,
        journal                                                  AS journal_name,
        NULL::TEXT                                               AS journal_issn,
        NULL::TEXT                                               AS volume,
        NULL::TEXT                                               AS issue,
        NULL::TEXT                                               AS first_page,
        NULL::TEXT                                               AS last_page,
        NULL::JSONB                                              AS author_names,
        authors                                                  AS authorships,
        NULL::JSONB                                              AS concepts,
        NULL::JSONB                                              AS keywords,
        -- mesh_terms stored as TEXT[] in raw; cast to JSONB for uniform schema
        to_jsonb(mesh_terms)                                     AS mesh_terms,
        NULL::INTEGER                                            AS cited_by_count,
        NULL::JSONB                                              AS citation_counts_by_year,
        NULL::BOOLEAN                                            AS is_open_access,
        NULL::TEXT                                               AS pdf_url,
        NULL::BOOLEAN                                            AS is_retracted,
        NULL::JSONB                                              AS grants,
        source,
        source_updated_at,
        created_at
    FROM bronze.pubmed
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- Cochrane systematic reviews
-- bronze.cochrane_reviews exposes: review_id, doi, title, abstract, publication_date,
-- review_type, authors (TEXT), interventions (TEXT[]), conditions (TEXT[]), conclusions
cochrane_pubs AS (
    SELECT
        'cochrane:' || review_id                                 AS openalex_id,
        doi,
        NULL::TEXT                                               AS pmid,
        NULL::TEXT                                               AS pmcid,
        title,
        abstract,
        review_type                                              AS publication_type,
        NULL::TEXT                                               AS language,
        EXTRACT(YEAR FROM publication_date)::INTEGER            AS publication_year,
        publication_date,
        'Cochrane Database of Systematic Reviews'                AS journal_name,
        NULL::TEXT                                               AS journal_issn,
        NULL::TEXT                                               AS volume,
        NULL::TEXT                                               AS issue,
        NULL::TEXT                                               AS first_page,
        NULL::TEXT                                               AS last_page,
        NULL::JSONB                                              AS author_names,
        -- authors stored as TEXT (semicolon-separated) in raw.cochrane_reviews
        to_jsonb(ARRAY[authors])                                 AS authorships,
        NULL::JSONB                                              AS concepts,
        NULL::JSONB                                              AS keywords,
        NULL::JSONB                                              AS mesh_terms,
        NULL::INTEGER                                            AS cited_by_count,
        NULL::JSONB                                              AS citation_counts_by_year,
        NULL::BOOLEAN                                            AS is_open_access,
        NULL::TEXT                                               AS pdf_url,
        NULL::BOOLEAN                                            AS is_retracted,
        NULL::JSONB                                              AS grants,
        source,
        source_updated_at,
        created_at
    FROM bronze.cochrane_reviews
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- Journal RSS feed entries
-- bronze.journal_rss now exposes flat columns: entry_id, doi, title, pub_date,
-- journal_name, summary (abstract), authors (TEXT)
journal_rss_pubs AS (
    SELECT
        'rss:' || entry_id                                       AS openalex_id,
        doi,
        NULL::TEXT                                               AS pmid,
        NULL::TEXT                                               AS pmcid,
        title,
        summary                                                  AS abstract,
        'journal-article'                                        AS publication_type,
        NULL::TEXT                                               AS language,
        EXTRACT(YEAR FROM pub_date)::INTEGER                    AS publication_year,
        pub_date                                                 AS publication_date,
        journal_name,
        NULL::TEXT                                               AS journal_issn,
        NULL::TEXT                                               AS volume,
        NULL::TEXT                                               AS issue,
        NULL::TEXT                                               AS first_page,
        NULL::TEXT                                               AS last_page,
        NULL::JSONB                                              AS author_names,
        to_jsonb(ARRAY[authors])                                 AS authorships,
        NULL::JSONB                                              AS concepts,
        NULL::JSONB                                              AS keywords,
        NULL::JSONB                                              AS mesh_terms,
        NULL::INTEGER                                            AS cited_by_count,
        NULL::JSONB                                              AS citation_counts_by_year,
        NULL::BOOLEAN                                            AS is_open_access,
        NULL::TEXT                                               AS pdf_url,
        NULL::BOOLEAN                                            AS is_retracted,
        NULL::JSONB                                              AS grants,
        source,
        source_updated_at,
        created_at
    FROM bronze.journal_rss
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- EuropePMC publications
-- bronze.europepmc exposes typed columns derived from mol_raw.europepmc_raw JSONB:
-- europepmc_pmid (TEXT), pmcid, doi, title, abstract, author_string, author_list (JSONB),
-- journal_title, publication_date (DATE), publication_year (INTEGER),
-- cited_by_count (INTEGER), is_open_access (BOOLEAN), mesh_terms (JSONB), keywords (JSONB)
europepmc_pubs AS (
    SELECT
        'europepmc:' || europepmc_pmid                           AS openalex_id,
        doi,
        europepmc_pmid                                           AS pmid,
        pmcid,
        title,
        abstract,
        publication_type,
        NULL::TEXT                                               AS language,
        publication_year,
        publication_date,
        journal_title                                            AS journal_name,
        journal_issn,
        NULL::TEXT                                               AS volume,
        NULL::TEXT                                               AS issue,
        NULL::TEXT                                               AS first_page,
        NULL::TEXT                                               AS last_page,
        NULL::JSONB                                              AS author_names,
        -- author_list from EuropePMC is an array of {fullName, ...} objects
        author_list                                              AS authorships,
        NULL::JSONB                                              AS concepts,
        keywords,
        mesh_terms,
        cited_by_count,
        NULL::JSONB                                              AS citation_counts_by_year,
        is_open_access,
        NULL::TEXT                                               AS pdf_url,
        NULL::BOOLEAN                                            AS is_retracted,
        NULL::JSONB                                              AS grants,
        source,
        source_updated_at,
        created_at
    FROM bronze.europepmc
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
    SELECT * FROM europepmc_pubs
    UNION ALL
    SELECT * FROM cochrane_pubs
    UNION ALL
    SELECT * FROM journal_rss_pubs
),

-- Extract first author and compute derived fields
enriched AS (
    SELECT
        *,
        -- First author info from JSONB authorships array
        -- OpenAlex:   authorships[0].author.display_name
        -- EuropePMC: authorships[0].fullName  (author_list field)
        -- PubMed/Cochrane/RSS: authorships is to_jsonb(ARRAY[text]) — single-element array
        CASE
            WHEN jsonb_typeof(authorships) = 'array'
                 AND authorships->0->'author' IS NOT NULL
            THEN authorships->0->'author'->>'display_name'
            WHEN jsonb_typeof(authorships) = 'array'
                 AND authorships->0->>'fullName' IS NOT NULL
            THEN authorships->0->>'fullName'
            WHEN jsonb_typeof(authorships) = 'array'
            THEN authorships->>0
            ELSE NULL
        END AS first_author_name,
        -- OpenAlex-sourced author ID (URL like https://openalex.org/A...)
        -- EuropePMC authorIds use different format; use authorId if available
        CASE
            WHEN authorships->0->'author' IS NOT NULL
            THEN authorships->0->'author'->>'id'
            WHEN authorships->0->>'authorId' IS NOT NULL
            THEN authorships->0->>'authorId'
            ELSE NULL
        END AS first_author_id,
        CASE
            WHEN authorships->0->'institutions' IS NOT NULL
            THEN authorships->0->'institutions'->0->>'display_name'
            ELSE NULL
        END AS first_author_institution,
        -- Author count
        COALESCE(jsonb_array_length(authorships), 0) AS author_count,
        -- Top concepts (only meaningful for OpenAlex)
        (SELECT jsonb_agg(c->>'display_name')
         FROM jsonb_array_elements(COALESCE(concepts, '[]'::JSONB)) AS c
         WHERE (c->>'score')::NUMERIC > 0.5
         LIMIT 5) AS top_concepts
    FROM combined_pubs
)

SELECT DISTINCT ON (doi)
    gen_random_uuid()       AS id,
    openalex_id,
    doi,
    pmid::BIGINT            AS pmid,
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
    first_author_id,
    first_author_institution,
    author_count,
    author_names,
    top_concepts            AS concepts,
    mesh_terms,
    cited_by_count,
    is_open_access,
    pdf_url,
    is_retracted,
    source,
    source_updated_at,
    NOW()                   AS created_at,
    NOW()                   AS updated_at
FROM enriched
ORDER BY doi,
    CASE source
        WHEN 'openalex'       THEN 1
        WHEN 'pubmed'         THEN 2
        WHEN 'europepmc'      THEN 3
        WHEN 'cochrane_reviews' THEN 4
        WHEN 'journal_rss'    THEN 5
        ELSE 6
    END;
