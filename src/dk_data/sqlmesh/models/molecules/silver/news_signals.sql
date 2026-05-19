-- SQLMesh Model: Silver News Signals
-- Normalized medical news and journal RSS signal data.
-- UNIONs mol_bronze.medical_news and mol_bronze.journal_rss into a single
-- signal table with molecule linkage via drug_mentions.
--
-- Field provenance:
--   mol_bronze.medical_news : article_id, source_name, title, summary, pub_date,
--                         url (source_url), drug_mentions JSONB (to_jsonb of TEXT[] raw),
--                         therapeutic_areas JSONB, source_updated_at
--   mol_bronze.journal_rss  : article_id, feed_source (->source_name), title,
--                         abstract (->summary), pub_date, link (->source_url),
--                         doi, categories JSONB (to_jsonb of TEXT[] raw), source_updated_at
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

-- Deduplicate across both sources before MERGE to prevent CardinalityViolation.
-- journal_rss bronze may contain the same article from multiple feed runs
-- (same source_url + pub_date with different bronze row IDs).
-- DISTINCT ON keeps the first occurrence per unique key.
WITH combined AS (
    -- Medical news branch
    SELECT
        article_id::TEXT                                          AS article_id,
        title::TEXT                                               AS title,
        source_name::TEXT                                         AS source_name,
        summary::TEXT                                             AS summary,
        pub_date::DATE                                            AS pub_date,
        url::TEXT                                                 AS source_url,
        NULL::TEXT                                                AS doi,
        NULL::TEXT                                                AS authors,
        -- drug_mentions is JSONB array in mol_bronze.medical_news (to_jsonb of TEXT[] raw col)
        CASE
            WHEN drug_mentions IS NOT NULL AND jsonb_array_length(drug_mentions) > 0
                THEN (SELECT string_agg(v, ', ') FROM jsonb_array_elements_text(drug_mentions) v)
            ELSE NULL
        END                                                       AS drug_mentions,
        CASE
            WHEN title ILIKE '%approval%' OR title ILIKE '%approved%' THEN 'regulatory'
            WHEN title ILIKE '%trial%'    OR title ILIKE '%study%'    THEN 'clinical'
            WHEN title ILIKE '%acquisition%' OR title ILIKE '%merger%' THEN 'corporate'
            ELSE 'general'
        END                                                       AS signal_type,
        -- therapeutic_areas is JSONB array in mol_bronze.medical_news
        CASE
            WHEN therapeutic_areas IS NOT NULL AND jsonb_array_length(therapeutic_areas) > 0
                THEN therapeutic_areas->>0
            ELSE NULL
        END                                                       AS therapeutic_area,
        -- Full therapeutic_areas JSONB array preserved for downstream multi-area lookups
        therapeutic_areas,
        NULL::JSONB                                               AS categories,
        NULL::NUMERIC                                             AS sentiment_score,
        'neutral'::TEXT                                           AS sentiment_polarity,
        source::TEXT                                              AS source,
        source_updated_at::TIMESTAMPTZ                            AS source_updated_at
    FROM mol_bronze.medical_news
    WHERE processed_to_silver = FALSE AND title IS NOT NULL

    UNION ALL

    -- Journal RSS branch
    SELECT
        article_id::TEXT                                          AS article_id,
        title::TEXT                                               AS title,
        feed_source::TEXT                                         AS source_name,
        abstract::TEXT                                            AS summary,
        pub_date::DATE                                            AS pub_date,
        link::TEXT                                                AS source_url,
        doi::TEXT                                                 AS doi,
        authors::TEXT                                             AS authors,
        -- journal_rss `categories` are RSS topic tags (e.g. "Oncology", "Clinical Trial"),
        -- NOT drug names. Setting to NULL prevents false matches in advocacy_sentiment
        -- when the gold model joins drug_mentions against mol_silver.molecules.canonical_name.
        NULL::TEXT                                                AS drug_mentions,
        CASE
            WHEN title ILIKE '%approval%' OR title ILIKE '%approved%' THEN 'regulatory'
            WHEN title ILIKE '%trial%'    OR title ILIKE '%study%'    THEN 'clinical'
            WHEN title ILIKE '%acquisition%' OR title ILIKE '%merger%' THEN 'corporate'
            ELSE 'general'
        END                                                       AS signal_type,
        NULL::TEXT                                                AS therapeutic_area,
        NULL::JSONB                                               AS therapeutic_areas,
        categories                                                AS categories,
        NULL::NUMERIC                                             AS sentiment_score,
        'neutral'::TEXT                                           AS sentiment_polarity,
        source::TEXT                                              AS source,
        source_updated_at::TIMESTAMPTZ                            AS source_updated_at
    FROM mol_bronze.journal_rss
    WHERE processed_to_silver = FALSE AND title IS NOT NULL
),

-- Deduplicate on the unique key (source_url, pub_date); keep any one row per pair.
deduped AS (
    SELECT DISTINCT ON (source_url, pub_date)
        article_id, title, source_name, summary, pub_date, source_url,
        doi, authors, drug_mentions,
        signal_type, therapeutic_area, therapeutic_areas, categories,
        sentiment_score, sentiment_polarity,
        source, source_updated_at
    FROM combined
    ORDER BY source_url, pub_date, source_updated_at DESC NULLS LAST
)

SELECT
    gen_random_uuid()   AS id,
    article_id,
    title,
    source_name,
    summary,
    pub_date,
    source_url,
    doi,
    authors,
    drug_mentions,
    signal_type,
    therapeutic_area,
    therapeutic_areas,
    categories,
    sentiment_score,
    sentiment_polarity,
    source,
    source_updated_at,
    NOW()               AS created_at,
    NOW()               AS updated_at
FROM deduped;
