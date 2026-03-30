-- SQLMesh Model: Silver Molecule Publications
-- Junction table linking molecules to scientific publications
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_silver.molecule_publications,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, publication_id)
    ),
    cron '@weekly',
    grain (molecule_id, publication_id),
    audits (
        not_null(columns := (molecule_id)),
        not_null(columns := (publication_id))
    )
);

-- Collect all molecule→publication links from all sources, then deduplicate.
-- INCREMENTAL_BY_UNIQUE_KEY uses MERGE on (molecule_id, publication_id).
-- Sources 1 and 3 (title/abstract ILIKE scans) require a GIN index on publications.title_tsv
-- to be performant; they are disabled until that index exists.
-- Active sources:
--   2: ChEMBL exact DOI/PubMed cross-references (highest confidence, O(1) lookup)
--   4: PubMed articles linked via MeSH terms / title match in mol_silver.pubmed_articles
WITH all_links AS (

    -- Source 2: ChEMBL cross-references (DOI/PubMed xref_id → publication) — exact match, fast
    SELECT DISTINCT
        m.molecule_id,
        p.id AS publication_id,
        'chembl_reference' AS link_type,
        1.0 AS confidence,
        'chembl' AS source
    FROM mol_silver.molecules m
    JOIN mol_bronze.chembl_molecules c ON (
        (m.inchi_key IS NOT NULL AND m.inchi_key = c.inchi_key)
        OR (m.inchi_key IS NULL AND LOWER(m.canonical_name) = LOWER(c.pref_name))
    )
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(c.cross_references, '[]'::JSONB)) AS xref
    JOIN mol_silver.publications p ON
        p.doi = xref->>'xref_id'
        OR p.pmid::TEXT = xref->>'xref_id'
    WHERE xref->>'xref_src' IN ('DOI', 'PubMed')
      AND xref->>'xref_id' IS NOT NULL

    UNION ALL

    -- Source 4: PubMed articles linked via MeSH terms / title match
    -- mol_silver.pubmed_articles has molecule_id set via MeSH term alias lookup;
    -- join to mol_silver.publications on PMID to get the canonical publication_id
    SELECT DISTINCT
        pa.molecule_id,
        p.id AS publication_id,
        'pubmed_mesh' AS link_type,
        0.85 AS confidence,
        'pubmed' AS source
    FROM mol_silver.pubmed_articles pa
    JOIN mol_silver.publications p
      ON p.pmid = pa.pmid::BIGINT
    WHERE pa.molecule_id IS NOT NULL
      AND p.id IS NOT NULL

),

deduped AS (
    SELECT DISTINCT ON (molecule_id, publication_id)
        molecule_id,
        publication_id,
        link_type,
        confidence,
        source
    FROM all_links
    WHERE molecule_id IS NOT NULL AND publication_id IS NOT NULL
    ORDER BY molecule_id, publication_id, confidence DESC NULLS LAST
)

SELECT
    molecule_id,
    publication_id,
    link_type,
    confidence,
    source,
    NOW() AS created_at
FROM deduped
