-- SQLMesh Model: Silver Cochrane Reviews
-- Promotes mol_bronze.cochrane_reviews into mol_silver.cochrane_reviews
-- Entity linking: LEFT JOIN mol_silver.molecules by canonical_name match in review title.
-- FULL refresh ensures molecule_id is always current when new molecules are added.
-- Exposes Cochrane systematic review meta-analyses to xenon section:
--   pivotal_trial_analysis (highest clinical evidence tier)

MODEL (
    name mol_silver.cochrane_reviews,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (review_id, title))
    )
);

SELECT
    gen_random_uuid()                       AS cochrane_silver_id,
    m.molecule_id,
    b.review_id,
    b.title,
    b.abstract,
    b.doi,
    b.publication_date AS pub_date,
    b.review_type,
    b.authors,
    -- raw_data: mol_raw.cochrane_reviews uses flat columns (no response_body JSONB stored)
    NULL::JSONB                             AS raw_data,
    'cochrane_reviews'                      AS source,
    b.created_at

FROM mol_bronze.cochrane_reviews b
LEFT JOIN mol_silver.molecules m
       ON LOWER(b.title) LIKE '%' || LOWER(m.canonical_name) || '%'
      AND LENGTH(m.canonical_name) > 4
WHERE b.review_id IS NOT NULL
  AND b.title IS NOT NULL;
