-- SQLMesh Model: Silver News Signals
-- Normalized medical news and media signal data
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name silver.news_signals,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source_url, pub_date)
    ),
    cron '@daily',
    audits (
        not_null(columns := (title, pub_date))
    ),
    grain (source_url, pub_date)
);

SELECT
    gen_random_uuid() AS id,
    title,
    source_name,
    pub_date,
    link AS source_url,
    drug_mentions,
    -- Derive sentiment polarity from raw sentiment field
    CASE
        WHEN sentiment ILIKE '%positive%' THEN 'positive'
        WHEN sentiment ILIKE '%negative%' THEN 'negative'
        ELSE 'neutral'
    END AS sentiment_polarity,
    NULL::NUMERIC AS sentiment_score,
    NULL::TEXT AS therapeutic_area,
    CASE
        WHEN title ILIKE '%approval%' OR title ILIKE '%approved%' THEN 'regulatory'
        WHEN title ILIKE '%trial%' OR title ILIKE '%study%' THEN 'clinical'
        WHEN title ILIKE '%acquisition%' OR title ILIKE '%merger%' THEN 'corporate'
        ELSE 'general'
    END AS signal_type,
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM bronze.medical_news
WHERE processed_to_silver = FALSE
  AND title IS NOT NULL;
