-- SQLMesh Model: Silver Cochrane Reviews
-- Promotes mol_bronze.cochrane_reviews into mol_silver.cochrane_reviews
-- with molecule-level linkage. molecule_id is NULL — entity linking fills it
-- by matching review title/abstract against mol_silver.molecules drug names.
-- Exposes Cochrane systematic review meta-analyses to xenon section:
--   pivotal_trial_analysis (highest clinical evidence tier)

MODEL (
    name mol_silver.cochrane_reviews,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (review_id)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (review_id, title))
    ),
    grain (review_id)
);

SELECT
    gen_random_uuid()                       AS cochrane_silver_id,
    NULL::UUID                              AS molecule_id,     -- entity linking fills this via title/abstract matching
    b.review_id,
    b.title,
    b.abstract,
    b.doi,
    CASE WHEN b.pub_date ~ '^\d{4}-\d{2}-\d{2}' THEN b.pub_date::DATE ELSE NULL END AS pub_date,
    b.review_type,
    b.authors,
    b.raw_json                              AS raw_data,
    'cochrane_reviews'                      AS source,
    b.created_at

FROM mol_bronze.cochrane_reviews b
WHERE b.processed_to_silver = FALSE
  AND b.review_id IS NOT NULL
  AND b.title IS NOT NULL;
