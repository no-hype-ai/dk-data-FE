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

-- Link molecules to publications via name matching
SELECT DISTINCT
    m.molecule_id AS molecule_id,
    p.id AS publication_id,
    'title_mention' AS link_type,
    1.0 AS confidence,
    p.source,
    NOW() AS created_at

FROM mol_silver.molecules m
JOIN mol_silver.molecule_aliases ma ON m.molecule_id = ma.molecule_id
JOIN mol_silver.publications p ON
    p.title ILIKE '%' || ma.alias_name || '%'
    OR p.abstract ILIKE '%' || ma.alias_name || '%'
WHERE m.needs_review = FALSE
  AND LENGTH(ma.alias_name) > 4  -- Avoid short aliases causing false matches

UNION ALL

-- Link from OpenAlex works mentioning drug names
SELECT DISTINCT
    m.molecule_id AS molecule_id,
    p.id AS publication_id,
    'openalex_match' AS link_type,
    0.8 AS confidence,
    'openalex' AS source,
    NOW() AS created_at

FROM mol_silver.molecules m
JOIN mol_silver.publications p ON
    p.title ILIKE '%' || m.canonical_name || '%'
WHERE m.needs_review = FALSE
  AND LENGTH(m.canonical_name) > 5
  AND p.source = 'openalex'
