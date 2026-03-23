-- SQLMesh Model: Silver Researchers
-- KOL/researcher profiles derived from OpenAlex + EuropePMC publication authorships.
-- No external API key required — sourced entirely from mol_silver.publications.
-- Unique key: OpenAlex author ID (e.g. https://openalex.org/A12345)

MODEL (
    name hcp_silver.researchers,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (author_id)),
        unique_values(columns := (author_id))
    )
);

-- Unnest all authorships from mol_silver.publications
WITH author_pubs AS (
    SELECT
        a->'author'->>'id'                    AS author_id,
        a->'author'->>'display_name'          AS display_name,
        a->'institutions'->0->>'display_name' AS institution,
        a->'institutions'->0->>'country_code' AS country,
        p.molecule_id,
        p.cited_by_count
    FROM mol_silver.publications p,
         jsonb_array_elements(COALESCE(p.authorships, '[]'::JSONB)) AS a
    WHERE a->'author'->>'id' IS NOT NULL
),

author_stats AS (
    SELECT
        author_id,
        MAX(display_name)                    AS display_name,
        MAX(institution)                     AS institution,
        MAX(country)                         AS country,
        COUNT(*)                             AS publication_count,
        COALESCE(SUM(cited_by_count), 0)     AS total_citations,
        COUNT(DISTINCT molecule_id)          AS molecule_count
    FROM author_pubs
    GROUP BY author_id
)

SELECT
    gen_random_uuid()                                              AS id,
    author_id,
    SPLIT_PART(display_name, ' ', 1)                              AS given_name,
    TRIM(SUBSTRING(display_name FROM POSITION(' ' IN display_name) + 1)) AS family_name,
    display_name                                                   AS full_name,
    institution                                                    AS affiliation,
    country,
    publication_count                                              AS works_count,
    total_citations,
    molecule_count,
    NULL::INTEGER                                                  AS h_index,
    NULL::JSONB                                                    AS research_areas,
    NULL::JSONB                                                    AS therapeutic_areas,
    NULL::INTEGER                                                  AS grant_count,
    'openalex'                                                     AS source,
    NOW()                                                          AS source_updated_at,
    NOW()                                                          AS created_at,
    NOW()                                                          AS updated_at
FROM author_stats
WHERE author_id IS NOT NULL;
