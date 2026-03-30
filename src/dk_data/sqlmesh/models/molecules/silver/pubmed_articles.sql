-- SQLMesh Model: Silver PubMed Articles
-- Promotes mol_bronze.pubmed into mol_silver.pubmed_articles with molecule_id linkage.
-- Entity linking:
--   Tier 1: MeSH term exact alias match — most reliable; MeSH terms are standardized
--           drug/compound headings stored as TEXT[] in mol_bronze.pubmed.mesh_terms
--   Tier 2: article title substring match via mol_silver.molecules.canonical_name
--           (length guard ≥ 6 chars prevents false positives on short names)
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
    -- Tier 1: MeSH term → alias_name_normalized exact match
    -- Tier 2: canonical_name substring in title (fallback for articles without drug MeSH terms)
    COALESCE(
        (
            SELECT ma.molecule_id
            FROM UNNEST(b.mesh_terms) AS mt(term)
            JOIN mol_silver.molecule_aliases ma
              ON LOWER(REGEXP_REPLACE(mt.term, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
            LIMIT 1
        ),
        (
            SELECT m2.molecule_id
            FROM mol_silver.molecules m2
            WHERE LOWER(b.title) LIKE '%' || LOWER(m2.canonical_name) || '%'
              AND LENGTH(m2.canonical_name) >= 6
            ORDER BY LENGTH(m2.canonical_name) DESC
            LIMIT 1
        )
    )                                                   AS molecule_id,
    b.pmid,
    b.title,
    b.abstract,
    b.authors,
    b.journal,
    b.publication_date,
    b.mesh_terms,
    b.doi,
    'pubmed'                                            AS source,
    b.source_updated_at,
    NOW()                                               AS created_at

FROM mol_bronze.pubmed b
WHERE b.pmid IS NOT NULL;
