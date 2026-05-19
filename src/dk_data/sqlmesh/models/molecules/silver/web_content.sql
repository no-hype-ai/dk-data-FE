-- SQLMesh Model: Silver Web Content
-- Promotes mol_bronze.websearch into mol_silver.web_content with molecule_id linkage.
-- Entity linking: search_query → mol_silver.molecules via canonical_name or alias.
-- Used for web signal enrichment during assessment runs.

MODEL (
    name mol_silver.web_content,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (search_query, result_url)
    ),
    cron '@daily',
    audits (
        not_null(columns := (result_url, search_query))
    )
);

SELECT DISTINCT ON (b.search_query, b.result_url)
    gen_random_uuid()                                   AS id,
    COALESCE(m_exact.molecule_id, m_alias.molecule_id) AS molecule_id,
    b.search_query,
    b.search_engine,
    b.search_type,
    b.result_url,
    b.result_title,
    b.result_snippet,
    b.result_rank,
    b.result_domain,
    b.publication_date,
    b.authors,
    b.source_name,
    b.relevance_score,
    'websearch'                                         AS source,
    b.ingested_at,
    b.source_updated_at,
    NOW()                                               AS created_at

FROM mol_bronze.websearch b
-- Link via exact canonical name match to search query
LEFT JOIN mol_silver.molecules m_exact
       ON b.search_query IS NOT NULL
      AND LOWER(m_exact.canonical_name) = LOWER(SPLIT_PART(b.search_query, ' ', 1))
-- Fallback: alias match on first word of query (drug name often first token)
LEFT JOIN mol_silver.molecule_names ma
       ON m_exact.molecule_id IS NULL
      AND b.search_query IS NOT NULL
      AND LOWER(REGEXP_REPLACE(SPLIT_PART(b.search_query, ' ', 1), '[^a-zA-Z0-9]', '', 'g'))
          = ma.normalized_name
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id
WHERE b.result_url IS NOT NULL
  AND b.search_query IS NOT NULL
ORDER BY b.search_query, b.result_url, b.source_updated_at DESC NULLS LAST;
