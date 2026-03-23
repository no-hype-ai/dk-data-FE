-- SQLMesh Model: Silver News Signals
-- Normalized medical news and media signal data
-- Entity linking: LEFT JOIN mol_silver.molecules by canonical_name match in title.
-- FULL refresh ensures molecule_id is always current when new molecules are added.
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_silver.news_signals,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (title, pub_date))
    )
);

SELECT
    gen_random_uuid() AS id,
    -- Entity link: resolve molecule_id by matching canonical_name in article title.
    -- NULL for articles with no known molecule mention. Length guard prevents false matches.
    m.molecule_id,
    b.article_id,
    b.title,
    b.source_name,
    b.pub_date,
    b.link,
    b.summary,
    b.drug_mentions,
    b.sentiment,
    -- Derive sentiment polarity from raw sentiment field
    CASE
        WHEN b.sentiment ILIKE '%positive%' THEN 'positive'
        WHEN b.sentiment ILIKE '%negative%' THEN 'negative'
        ELSE 'neutral'
    END AS sentiment_polarity,
    NULL::NUMERIC AS sentiment_score,
    NULL::TEXT AS therapeutic_area,
    CASE
        WHEN b.title ILIKE '%approval%' OR b.title ILIKE '%approved%' THEN 'regulatory'
        WHEN b.title ILIKE '%trial%' OR b.title ILIKE '%study%' THEN 'clinical'
        WHEN b.title ILIKE '%acquisition%' OR b.title ILIKE '%merger%' THEN 'corporate'
        ELSE 'general'
    END AS signal_type,
    b.id AS bronze_id,
    b.source,
    b.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM mol_bronze.medical_news b
LEFT JOIN mol_silver.molecules m
       ON LOWER(b.title) LIKE '%' || LOWER(m.canonical_name) || '%'
      AND LENGTH(m.canonical_name) > 4
WHERE processed_to_silver = FALSE
  AND title IS NOT NULL;
