-- SQLMesh Model: Bronze Cochrane Reviews
-- Transforms flat mol_raw.cochrane_reviews typed columns to Bronze canonical schema
-- mol_raw.cochrane_reviews is populated by CochraneFetcher + load_cochrane_data()
-- Columns are typed at load time — no JSON path drilling needed here.
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_bronze.cochrane_reviews,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key review_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (review_id)),
        unique_values(columns := (review_id))
    ),
    grain review_id
);

SELECT
    gen_random_uuid()            AS id,

    -- Review identifiers (flat typed columns from mol_raw.cochrane_reviews)
    r.review_id::TEXT            AS review_id,
    r.title::TEXT                AS title,
    r.authors::TEXT              AS authors,
    r.abstract::TEXT             AS abstract,
    r.publication_date::DATE     AS publication_date,
    r.doi::TEXT                  AS doi,
    r.pmid::TEXT                 AS pmid,
    r.review_type::TEXT          AS review_type,

    -- Intervention and condition arrays
    r.interventions::TEXT[]      AS interventions,
    r.conditions::TEXT[]         AS conditions,
    r.conclusions::TEXT          AS conclusions,

    -- Source tracking
    'cochrane_reviews'           AS source,
    r._loaded_at                 AS source_updated_at,
    FALSE                        AS processed_to_silver,
    NOW()                        AS created_at

FROM mol_raw.cochrane_reviews r
WHERE
    r.review_id IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;
