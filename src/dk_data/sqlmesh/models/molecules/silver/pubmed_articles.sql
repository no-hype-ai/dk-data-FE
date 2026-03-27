-- SQLMesh Model: Silver PubMed Articles
-- Promotes mol_bronze.pubmed into mol_silver.pubmed_articles with molecule_id linkage.
-- Entity linking: search query from request_params → canonical_name / alias.
-- Complements mol_silver.publications (OpenAlex/EuropePMC) with direct PubMed data.

MODEL (
    name mol_silver.pubmed_articles,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key pmid
    ),
    cron '@daily',
    audits (
        not_null(columns := (pmid))
    ),
    grain pmid
);

SELECT
    gen_random_uuid()                                   AS id,
    COALESCE(m_exact.molecule_id, m_alias.molecule_id) AS molecule_id,
    b.pmid,
    b.title,
    b.abstract,
    b.authors,
    b.journal,
    -- Normalise pub_date to DATE (PubMed sortpubdate: "YYYY/MM/DD HH:MM")
    CASE
        WHEN b.pub_date ~ '^\d{4}/\d{2}/\d{2}'
        THEN TO_DATE(LEFT(b.pub_date, 10), 'YYYY/MM/DD')
        WHEN b.pub_date ~ '^\d{4}'
        THEN TO_DATE(LEFT(b.pub_date, 4), 'YYYY')
        ELSE NULL
    END                                                 AS publication_date,
    b.mesh_terms,
    b.doi,
    'pubmed'                                            AS source,
    b.source_updated_at,
    NOW()                                               AS created_at

FROM mol_bronze.pubmed b
-- Link via drug name stored in request_params (set by ingestion query)
LEFT JOIN mol_silver.molecules m_exact
       ON b.raw_json->>'query_drug' IS NOT NULL
      AND LOWER(m_exact.canonical_name) = LOWER(b.raw_json->>'query_drug')
LEFT JOIN mol_silver.molecule_aliases ma
       ON m_exact.molecule_id IS NULL
      AND b.raw_json->>'query_drug' IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.raw_json->>'query_drug', '[^a-zA-Z0-9]', '', 'g'))
          = ma.alias_name_normalized
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id
WHERE b.pmid IS NOT NULL;
