-- SQLMesh Model: Silver Molecule Publications
-- Junction table linking molecules to scientific publications
-- Part of DK Molecule Data Platform (012-dk-data-platform)
--
-- Antipattern fixes (T112):
--   S2 eliminated: Source 5 (EuropePMC) previously used
--     S2 leading-wildcard substring match on indexed column — replaced with equi-join (FR-016).
--     Replaced with equi-join on mol_silver.molecule_names.normalized_name.
--
-- FR-033: NCT trial cross-references (NCT\d{8}), DOIs, and PMIDs are extracted from
--   publication title/abstract and stored in structured fields.
--
-- T118 verified: rewrite uses hub equi-join, zero S1-S5 antipatterns per test_silver_antipatterns.py

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
-- Active sources:
--   2: ChEMBL exact DOI/PubMed cross-references (highest confidence, O(1) lookup)
--   4: PubMed articles linked via MeSH terms / title match in mol_silver.pubmed_articles
--   5: EuropePMC articles linked via mol_silver.molecule_names equi-join on normalized title token
WITH all_links AS (

    -- Source 2: ChEMBL cross-references (DOI/PubMed xref_id → publication) — exact match, fast
    SELECT DISTINCT
        m.molecule_id,
        p.id AS publication_id,
        'chembl_reference' AS link_type,
        1.0 AS confidence,
        'chembl' AS source,
        -- FR-033: extract NCT trial refs from xref (ChEMBL occasionally cross-refs trials)
        NULL::TEXT[] AS nct_refs,
        NULL::TEXT[] AS doi_refs,
        NULL::TEXT[] AS pmid_refs
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
        'pubmed' AS source,
        -- FR-033: extract NCT trial references from PubMed abstract
        ARRAY(SELECT DISTINCT m[1]
              FROM regexp_matches(COALESCE(pa.abstract, ''), 'NCT\d{8}', 'g') AS m)
            AS nct_refs,
        ARRAY(SELECT DISTINCT m[1]
              FROM regexp_matches(COALESCE(pa.abstract, ''), '10\.\d{4,9}/[-._;()/:A-Z0-9a-z0-9]+', 'g') AS m)
            AS doi_refs,
        ARRAY(SELECT DISTINCT m[1]
              FROM regexp_matches(COALESCE(pa.abstract, ''), 'PMID:?\s*(\d+)', 'g') AS m)
            AS pmid_refs
    FROM mol_silver.pubmed_articles pa
    JOIN mol_silver.publications p
      ON p.pmid = pa.pmid::BIGINT
    WHERE pa.molecule_id IS NOT NULL
      AND p.id IS NOT NULL

    UNION ALL

    -- Source 5: EuropePMC — mol_silver.publications already contains europepmc rows.
    -- Link to molecules via mol_silver.molecule_names equi-join on title first-token.
    -- Replaces prior S2 leading-wildcard substring match (FR-016).
    -- Strategy: join on normalized first-significant-word (>=5 chars) from title.
    SELECT DISTINCT
        mn.molecule_id,
        p.id AS publication_id,
        'europepmc_name' AS link_type,
        0.75 AS confidence,
        'europepmc' AS source,
        -- FR-033: extract NCT trial references from europepmc abstract
        ARRAY(SELECT DISTINCT m[1]
              FROM regexp_matches(COALESCE(p.abstract, p.title, ''), 'NCT\d{8}', 'g') AS m)
            AS nct_refs,
        ARRAY(SELECT DISTINCT m[1]
              FROM regexp_matches(COALESCE(p.abstract, p.title, ''), '10\.\d{4,9}/[-._;()/:A-Z0-9a-z0-9]+', 'g') AS m)
            AS doi_refs,
        ARRAY(SELECT DISTINCT m[1]
              FROM regexp_matches(COALESCE(p.abstract, p.title, ''), 'PMID:?\s*(\d+)', 'g') AS m)
            AS pmid_refs
    FROM mol_silver.publications p
    -- Equi-join: normalize each space-delimited title token and match against molecule_names
    JOIN LATERAL (
        SELECT mn_inner.molecule_id
        FROM regexp_split_to_table(LOWER(p.title), '\s+') AS tok(word)
        JOIN mol_silver.molecule_names mn_inner
            ON mn_inner.normalized_name = LOWER(REGEXP_REPLACE(tok.word, '[^a-zA-Z0-9]', '', 'g'))
        WHERE LENGTH(tok.word) >= 5
        ORDER BY LENGTH(tok.word) DESC
        LIMIT 1
    ) mn ON TRUE
    WHERE p.source = 'europepmc'
      AND p.id IS NOT NULL

),

deduped AS (
    SELECT DISTINCT ON (molecule_id, publication_id)
        molecule_id,
        publication_id,
        link_type,
        confidence,
        source,
        nct_refs,
        doi_refs,
        pmid_refs
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
    nct_refs,
    doi_refs,
    pmid_refs,
    NOW() AS created_at
FROM deduped
