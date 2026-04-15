-- SQLMesh Model: Silver Publications
-- Normalized publication data from OpenAlex, PubMed, Cochrane, and Journal RSS
-- Reads from mol_bronze.* models which themselves read from flat mol_raw.* typed tables.
-- Part of: 012-dk-data-platform (extended by 015-assessment-dashboard-integration)

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
        topics,
        keywords,
        mesh_terms,
        cited_by_count,
        cited_by_percentile,
        citation_counts_by_year,
        is_open_access,
        pdf_url,
        is_retracted,
        is_paratext,
        grants,
        referenced_works,
        related_works,
        sustainable_development_goals,
        NULL::JSONB AS publication_types,
        NULL::TEXT  AS conclusions,
        NULL::JSONB AS interventions_reviewed,
        NULL::JSONB AS conditions_reviewed,
        source,
        source_updated_at,
        created_at
    FROM mol_bronze.openalex
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- PubMed publications
-- mol_bronze.pubmed now exposes flat columns: pmid, doi, title, abstract, journal,
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
        NULL::JSONB                                              AS topics,
        -- keywords stored as TEXT[] in raw; cast to JSONB for uniform schema
        keywords                                                 AS keywords,
        -- mesh_terms stored as TEXT[] in raw; cast to JSONB for uniform schema
        to_jsonb(mesh_terms)                                     AS mesh_terms,
        NULL::INTEGER                                            AS cited_by_count,
        NULL::NUMERIC                                            AS cited_by_percentile,
        NULL::JSONB                                              AS citation_counts_by_year,
        NULL::BOOLEAN                                            AS is_open_access,
        NULL::TEXT                                               AS pdf_url,
        NULL::BOOLEAN                                            AS is_retracted,
        NULL::BOOLEAN                                            AS is_paratext,
        NULL::JSONB                                              AS grants,
        NULL::JSONB                                              AS referenced_works,
        NULL::JSONB                                              AS related_works,
        NULL::JSONB                                              AS sustainable_development_goals,
        -- publication_types stored as TEXT[] in raw; cast to JSONB for uniform schema
        publication_types                                        AS publication_types,
        NULL::TEXT                                               AS conclusions,
        NULL::JSONB                                              AS interventions_reviewed,
        NULL::JSONB                                              AS conditions_reviewed,
        source,
        source_updated_at,
        created_at
    FROM mol_bronze.pubmed
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- Cochrane systematic reviews
-- mol_bronze.cochrane_reviews exposes: review_id, doi, title, abstract, publication_date,
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
        -- authors stored as TEXT (semicolon-separated) in mol_raw.cochrane_reviews
        to_jsonb(ARRAY[authors])                                 AS authorships,
        NULL::JSONB                                              AS concepts,
        NULL::JSONB                                              AS topics,
        NULL::JSONB                                              AS keywords,
        NULL::JSONB                                              AS mesh_terms,
        NULL::INTEGER                                            AS cited_by_count,
        NULL::NUMERIC                                            AS cited_by_percentile,
        NULL::JSONB                                              AS citation_counts_by_year,
        NULL::BOOLEAN                                            AS is_open_access,
        NULL::TEXT                                               AS pdf_url,
        NULL::BOOLEAN                                            AS is_retracted,
        NULL::BOOLEAN                                            AS is_paratext,
        NULL::JSONB                                              AS grants,
        NULL::JSONB                                              AS referenced_works,
        NULL::JSONB                                              AS related_works,
        NULL::JSONB                                              AS sustainable_development_goals,
        NULL::JSONB                                              AS publication_types,
        conclusions,
        -- interventions and conditions are TEXT[] in bronze; cast to JSONB array for uniform schema
        to_jsonb(interventions)                                  AS interventions_reviewed,
        to_jsonb(conditions)                                     AS conditions_reviewed,
        source,
        source_updated_at,
        created_at
    FROM mol_bronze.cochrane_reviews
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- Journal RSS feed entries
-- mol_bronze.journal_rss now exposes flat columns: article_id, doi, title, pub_date,
-- journal_name, summary (abstract), authors (TEXT)
journal_rss_pubs AS (
    SELECT
        'rss:' || article_id                                       AS openalex_id,
        doi,
        NULL::TEXT                                               AS pmid,
        NULL::TEXT                                               AS pmcid,
        title,
        abstract,
        'journal-article'                                        AS publication_type,
        NULL::TEXT                                               AS language,
        EXTRACT(YEAR FROM pub_date)::INTEGER                    AS publication_year,
        pub_date                                                 AS publication_date,
        feed_source                                              AS journal_name,
        NULL::TEXT                                               AS journal_issn,
        NULL::TEXT                                               AS volume,
        NULL::TEXT                                               AS issue,
        NULL::TEXT                                               AS first_page,
        NULL::TEXT                                               AS last_page,
        NULL::JSONB                                              AS author_names,
        to_jsonb(ARRAY[authors])                                 AS authorships,
        NULL::JSONB                                              AS concepts,
        NULL::JSONB                                              AS topics,
        categories                                               AS keywords,
        NULL::JSONB                                              AS mesh_terms,
        NULL::INTEGER                                            AS cited_by_count,
        NULL::NUMERIC                                            AS cited_by_percentile,
        NULL::JSONB                                              AS citation_counts_by_year,
        NULL::BOOLEAN                                            AS is_open_access,
        NULL::TEXT                                               AS pdf_url,
        NULL::BOOLEAN                                            AS is_retracted,
        NULL::BOOLEAN                                            AS is_paratext,
        NULL::JSONB                                              AS grants,
        NULL::JSONB                                              AS referenced_works,
        NULL::JSONB                                              AS related_works,
        NULL::JSONB                                              AS sustainable_development_goals,
        NULL::JSONB                                              AS publication_types,
        NULL::TEXT                                               AS conclusions,
        NULL::JSONB                                              AS interventions_reviewed,
        NULL::JSONB                                              AS conditions_reviewed,
        source,
        source_updated_at,
        created_at
    FROM mol_bronze.journal_rss
    WHERE
        processed_to_silver = FALSE
        AND title IS NOT NULL
),

-- EuropePMC publications
-- mol_bronze.europepmc exposes typed columns derived from mol_raw.europepmc JSONB:
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
        volume,
        issue,
        first_page,
        last_page,
        NULL::JSONB                                              AS author_names,
        -- author_list from EuropePMC is an array of {fullName, ...} objects
        author_list                                              AS authorships,
        NULL::JSONB                                              AS concepts,
        NULL::JSONB                                              AS topics,
        keywords,
        mesh_terms,
        cited_by_count,
        NULL::NUMERIC                                            AS cited_by_percentile,
        NULL::JSONB                                              AS citation_counts_by_year,
        is_open_access,
        NULL::TEXT                                               AS pdf_url,
        NULL::BOOLEAN                                            AS is_retracted,
        NULL::BOOLEAN                                            AS is_paratext,
        NULL::JSONB                                              AS grants,
        NULL::JSONB                                              AS referenced_works,
        NULL::JSONB                                              AS related_works,
        NULL::JSONB                                              AS sustainable_development_goals,
        NULL::JSONB                                              AS publication_types,
        NULL::TEXT                                               AS conclusions,
        NULL::JSONB                                              AS interventions_reviewed,
        NULL::JSONB                                              AS conditions_reviewed,
        source,
        source_updated_at,
        created_at
    FROM mol_bronze.europepmc
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
        combined_pubs.*,
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

-- DISTINCT ON (doi): requires doi IS NOT NULL — NULL doi rows cannot be deduplicated
-- and would collapse all null-doi publications into one arbitrary record.
-- Publications without a DOI are excluded; they lack the identifier needed for
-- INCREMENTAL_BY_UNIQUE_KEY merges and downstream citation linkage.
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
    topics,
    keywords,
    mesh_terms,
    cited_by_count,
    cited_by_percentile,
    is_open_access,
    pdf_url,
    is_retracted,
    is_paratext,
    referenced_works,
    related_works,
    sustainable_development_goals,
    publication_types,
    conclusions,
    interventions_reviewed,
    conditions_reviewed,
    -- Evidence tier classification (A-D, U=unclassified, never NULL)
    CASE
        WHEN source = 'cochrane_reviews'
             OR publication_type ILIKE '%systematic review%'
             OR publication_type ILIKE '%meta-analysis%'
        THEN 'A'
        WHEN publication_type ILIKE '%randomized%'
             OR publication_type ILIKE '%clinical trial%'
             OR publication_type ILIKE '%controlled%'
        THEN 'B'
        WHEN publication_type ILIKE '%observational%'
             OR publication_type ILIKE '%cohort%'
             OR publication_type ILIKE '%case-control%'
             OR publication_type ILIKE '%real-world%'
        THEN 'C'
        WHEN publication_type ILIKE '%case report%'
             OR publication_type ILIKE '%editorial%'
             OR publication_type ILIKE '%comment%'
             OR publication_type ILIKE '%letter%'
             OR publication_type ILIKE '%opinion%'
        THEN 'D'
        ELSE 'U'
    END::VARCHAR(1)         AS evidence_tier,
    source,
    source_updated_at,
    NOW()                   AS created_at,
    NOW()                   AS updated_at
FROM enriched
WHERE doi IS NOT NULL
ORDER BY doi,
    CASE source
        WHEN 'openalex'       THEN 1
        WHEN 'pubmed'         THEN 2
        WHEN 'europepmc'      THEN 3
        WHEN 'cochrane_reviews' THEN 4
        WHEN 'journal_rss'    THEN 5
        ELSE 6
    END;
