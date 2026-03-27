-- SQLMesh Model: Silver News Signals
-- Normalized medical news and journal RSS signal data.
-- UNIONs mol_bronze.medical_news and mol_bronze.journal_rss into a single
-- signal table with molecule linkage via drug_mentions.
--
-- Field provenance:
--   mol_bronze.medical_news : article_id, source_name, title, summary, pub_date,
--                         url (source_url), drug_mentions TEXT[],
--                         therapeutic_areas TEXT[], source_updated_at
--   mol_bronze.journal_rss  : article_id, feed_source (->source_name), title,
--                         abstract (->summary), pub_date, link (->source_url),
--                         doi, categories TEXT[], source_updated_at
--
-- Part of: 011-datasource-integration / 015-assessment-dashboard-integration

MODEL (
    name mol_silver.news_signals,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (source_url, pub_date)
    ),
    cron '@daily',
    audits (
        not_null(columns := (title, pub_date))
    ),
    grain (source_url, pub_date)
);

-- Medical news branch
SELECT
    gen_random_uuid()                                          AS id,
    title::TEXT                                               AS title,
    source_name::TEXT                                         AS source_name,
    pub_date::DATE                                            AS pub_date,
    url::TEXT                                                 AS source_url,
    -- drug_mentions is TEXT[]; convert to comma-delimited text for the silver
    -- denormalised column so downstream consumers get a scalar
    CASE
        WHEN drug_mentions IS NOT NULL AND array_length(drug_mentions, 1) > 0
            THEN array_to_string(drug_mentions, ', ')
        ELSE NULL
    END                                                       AS drug_mentions,
    -- Derive signal type from title keywords
    CASE
        WHEN title ILIKE '%approval%' OR title ILIKE '%approved%' THEN 'regulatory'
        WHEN title ILIKE '%trial%'    OR title ILIKE '%study%'    THEN 'clinical'
        WHEN title ILIKE '%acquisition%' OR title ILIKE '%merger%' THEN 'corporate'
        ELSE 'general'
    END                                                       AS signal_type,
    -- Therapeutic area: take the first element of the array (most relevant)
    CASE
        WHEN therapeutic_areas IS NOT NULL AND array_length(therapeutic_areas, 1) > 0
            THEN therapeutic_areas[1]
        ELSE NULL
    END                                                       AS therapeutic_area,
    NULL::NUMERIC                                             AS sentiment_score,
    'neutral'::TEXT                                           AS sentiment_polarity,
    source::TEXT                                              AS source,
    source_updated_at::TIMESTAMPTZ                            AS source_updated_at,
    NOW()                                                     AS created_at,
    NOW()                                                     AS updated_at

FROM mol_bronze.medical_news
WHERE
    processed_to_silver = FALSE
    AND title IS NOT NULL

UNION ALL

-- Journal RSS branch
SELECT
    gen_random_uuid()                                          AS id,
    title::TEXT                                               AS title,
    feed_source::TEXT                                         AS source_name,
    pub_date::DATE                                            AS pub_date,
    link::TEXT                                                AS source_url,
    -- Journal RSS has no drug_mentions; use categories as a proxy label
    CASE
        WHEN categories IS NOT NULL AND array_length(categories, 1) > 0
            THEN array_to_string(categories, ', ')
        ELSE NULL
    END                                                       AS drug_mentions,
    -- Derive signal type from title keywords (same logic)
    CASE
        WHEN title ILIKE '%approval%' OR title ILIKE '%approved%' THEN 'regulatory'
        WHEN title ILIKE '%trial%'    OR title ILIKE '%study%'    THEN 'clinical'
        WHEN title ILIKE '%acquisition%' OR title ILIKE '%merger%' THEN 'corporate'
        ELSE 'general'
    END                                                       AS signal_type,
    -- Journal RSS has no therapeutic_areas; set null
    NULL::TEXT                                                AS therapeutic_area,
    NULL::NUMERIC                                             AS sentiment_score,
    'neutral'::TEXT                                           AS sentiment_polarity,
    source::TEXT                                              AS source,
    source_updated_at::TIMESTAMPTZ                            AS source_updated_at,
    NOW()                                                     AS created_at,
    NOW()                                                     AS updated_at

FROM mol_bronze.journal_rss
WHERE
    processed_to_silver = FALSE
    AND title IS NOT NULL;
