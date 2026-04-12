-- SQLMesh Model: Silver Cochrane Reviews
-- Promotes mol_bronze.cochrane_reviews into mol_silver.cochrane_reviews
-- Entity linking: LEFT JOIN mol_silver.molecules by canonical_name match in review title.
-- FULL refresh ensures molecule_id is always current when new molecules are added.
-- Exposes Cochrane systematic review meta-analyses to xenon section:
--   pivotal_trial_analysis (highest clinical evidence tier)

MODEL (
    name mol_silver.cochrane_reviews,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key review_id
    ),
    cron '@monthly',
    audits (
        not_null(columns := (review_id, title))
    ),
    grain review_id,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (b.review_id)
    gen_random_uuid()                       AS cochrane_silver_id,
    m.molecule_id    AS molecule_id,
    b.review_id,
    b.pmid,
    b.title,
    b.abstract,
    b.doi,
    b.publication_date,
    b.review_type,
    b.authors,
    b.interventions,
    b.conditions,
    b.conclusions,
    -- raw_data: mol_raw.cochrane_reviews uses flat columns (no response_body JSONB stored)
    NULL::JSONB                             AS raw_data,
    'cochrane_reviews'                      AS source,
    b.source_updated_at,
    b.created_at

FROM mol_bronze.cochrane_reviews b
-- S2 fix (FR-016): replace leading-wildcard LIKE with trigram similarity on molecule_names hub.
-- similarity() uses a GIN pg_trgm index on normalized_name — no sequential scan.
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE LENGTH(mn.normalized_name) > 4
      AND similarity(LOWER(b.title), mn.normalized_name) >= 0.3
    ORDER BY similarity(LOWER(b.title), mn.normalized_name) DESC
    LIMIT 1
) m ON TRUE
WHERE b.review_id IS NOT NULL
  AND b.title IS NOT NULL
ORDER BY b.review_id, m.molecule_id NULLS LAST;
