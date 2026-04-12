-- SQLMesh Model: Silver PubMed Articles
-- Promotes mol_bronze.pubmed into mol_silver.pubmed_articles with molecule_id linkage.
-- Entity linking:
--   Tier 1: MeSH term equi-join via mol_silver.molecule_names (normalized MeSH term)
--           Most reliable; MeSH terms are standardized drug/compound headings.
--   Tier 2: title token equi-join via mol_silver.molecule_names (first matching word >= 6 chars)
--           Fallback for articles without drug MeSH terms.
--           Uses trigram similarity only as secondary tier — no leading-wildcard LIKE.
-- Complements mol_silver.publications (OpenAlex/EuropePMC) with direct PubMed data.
--
-- Antipattern fixes (T113):
--   S3 eliminated: prior COALESCE used correlated scalar subquery over jsonb_array_elements_text.
--                  Replaced with LEFT JOIN LATERAL (mesh_link).
--   S2 eliminated: prior Tier 2 used leading-wildcard substring match (FR-016) — replaced with LATERAL join.
--                  Replaced with LEFT JOIN LATERAL over title tokens (equi-join on normalized form).
--
-- FR-033: NCT trial cross-refs extracted from abstract via regexp_matches.
-- Condition linkage: MeSH terms joined to ind_silver.condition_identifiers (source='mesh').
--
-- T118 verified: rewrite uses hub equi-join, zero S1-S5 antipatterns per test_silver_antipatterns.py

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

SELECT DISTINCT ON (b.pmid)
    gen_random_uuid()                                   AS id,
    -- Tier 1: MeSH term → molecule_names equi-join (normalized MeSH term, strip non-alnum)
    -- Replaces correlated scalar subquery (S3) over molecule_aliases.
    -- Tier 2: title token → molecule_names equi-join (fallback, no leading-wildcard LIKE)
    -- Replaces leading-wildcard LIKE (S2) over molecules.canonical_name.
    COALESCE(mesh_link.molecule_id, title_link.molecule_id) AS molecule_id,
    b.pmid,
    b.title,
    b.abstract,
    b.authors,
    b.journal,
    b.publication_date,
    b.mesh_terms,
    b.publication_types,
    b.keywords,
    b.doi,
    -- FR-033: NCT\d{8} trial cross-references extracted from abstract
    ARRAY(SELECT DISTINCT m[1]
          FROM regexp_matches(COALESCE(b.abstract, ''), 'NCT\d{8}', 'g') AS m)
        AS nct_trial_refs,
    -- Condition linkage via MeSH terms → ind_silver.condition_identifiers (source='mesh')
    cond_link.condition_id,
    'pubmed'                                            AS source,
    b.source_updated_at,
    NOW()                                               AS created_at

FROM mol_bronze.pubmed b

-- Tier 1: MeSH → molecule_names equi-join (replaces S3 correlated subquery)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM jsonb_array_elements_text(COALESCE(b.mesh_terms, '[]'::JSONB)) AS mt(term)
    JOIN mol_silver.molecule_names mn
        ON mn.normalized_name = LOWER(REGEXP_REPLACE(mt.term, '[^a-zA-Z0-9]', '', 'g'))
    ORDER BY mn.molecule_id
    LIMIT 1
) mesh_link ON TRUE

-- Tier 2: title tokens → molecule_names equi-join (replaces S2 leading-wildcard LIKE)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM regexp_split_to_table(LOWER(b.title), '\s+') AS tok(word)
    JOIN mol_silver.molecule_names mn
        ON mn.normalized_name = LOWER(REGEXP_REPLACE(tok.word, '[^a-zA-Z0-9]', '', 'g'))
    WHERE LENGTH(tok.word) >= 6
    ORDER BY LENGTH(tok.word) DESC
    LIMIT 1
) title_link ON mesh_link.molecule_id IS NULL

-- Condition linkage: MeSH terms → ind_silver.condition_identifiers (source='mesh')
LEFT JOIN LATERAL (
    SELECT ci.condition_id
    FROM jsonb_array_elements_text(COALESCE(b.mesh_terms, '[]'::JSONB)) AS mt(term)
    JOIN ind_silver.condition_identifiers ci
        ON ci.source = 'mesh'
        AND UPPER(ci.identifier) = UPPER(mt.term)
    LIMIT 1
) cond_link ON TRUE

WHERE b.pmid IS NOT NULL
ORDER BY b.pmid, b.source_updated_at DESC NULLS LAST;
