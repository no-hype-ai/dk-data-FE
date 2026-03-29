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
-- A MERGE fails (CardinalityViolation) when the source batch has two rows with
-- the same (molecule_id, publication_id). This happens when:
--   • The same publication matches multiple aliases of the same molecule, OR
--   • Multiple UNION branches independently link the same pair.
-- The DISTINCT ON at the end keeps the highest-confidence link per pair.
WITH all_links AS (

    -- Source 1: title/abstract mention via molecule aliases
    SELECT DISTINCT
        m.molecule_id,
        p.id AS publication_id,
        'title_mention' AS link_type,
        1.0 AS confidence,
        p.source
    FROM mol_silver.molecules m
    JOIN mol_silver.molecule_aliases ma ON m.molecule_id = ma.molecule_id
    JOIN mol_silver.publications p ON
        p.title ILIKE '%' || ma.alias_name || '%'
        OR p.abstract ILIKE '%' || ma.alias_name || '%'
    WHERE LENGTH(ma.alias_name) > 4

    UNION ALL

    -- Source 2: ChEMBL cross-references (DOI/PubMed xref_id → publication)
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

    -- Source 3: OpenAlex canonical name match in publication title
    SELECT DISTINCT
        m.molecule_id,
        p.id AS publication_id,
        'openalex_match' AS link_type,
        0.8 AS confidence,
        'openalex' AS source
    FROM mol_silver.molecules m
    JOIN mol_silver.publications p ON
        p.title ILIKE '%' || m.canonical_name || '%'
    WHERE LENGTH(m.canonical_name) > 5
      AND p.source = 'openalex'

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
