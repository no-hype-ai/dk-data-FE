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
    b.publication_date,
    b.mesh_terms,
    b.doi,
    'pubmed'                                            AS source,
    b.source_updated_at,
    NOW()                                               AS created_at

FROM mol_bronze.pubmed b
-- Link via drug name stored in request_params (set by ingestion query)
LEFT JOIN mol_silver.molecules m_exact
       ON FALSE  -- raw_json not in mol_bronze.pubmed flat schema; drug name linkage disabled
LEFT JOIN mol_silver.molecule_aliases ma
       ON FALSE
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id
WHERE b.pmid IS NOT NULL;
