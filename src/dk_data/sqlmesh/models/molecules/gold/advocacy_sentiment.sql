-- SQLMesh Model: Gold Advocacy Sentiment
-- Aggregated sentiment signals per molecule from news and media sources
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_gold.advocacy_sentiment,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, source)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (molecule_id, source))
    ),
    grain (molecule_id, source)
);

-- Link news signals to molecules via drug_mentions
WITH molecule_signals AS (
    SELECT
        m.id AS molecule_id,
        ns.source_name AS source,
        ns.sentiment_polarity,
        ns.signal_type,
        ns.title,
        ns.pub_date,
        ns.source_url
    FROM silver.news_signals ns
    CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(ns.drug_mentions, '[]'::JSONB)) AS dm
    JOIN silver.molecules m
        ON LOWER(dm) = LOWER(m.canonical_name)
    WHERE ns.drug_mentions IS NOT NULL
),

-- Aggregate per molecule-source pair
aggregated AS (
    SELECT
        molecule_id,
        source,
        -- Overall sentiment polarity (majority vote)
        MODE() WITHIN GROUP (ORDER BY sentiment_polarity) AS sentiment_polarity,
        COUNT(*) AS signal_count,
        -- Recent top 10 signals as JSONB array
        (
            SELECT jsonb_agg(signal_obj)
            FROM (
                SELECT jsonb_build_object(
                    'title', ms2.title,
                    'pub_date', ms2.pub_date,
                    'sentiment', ms2.sentiment_polarity,
                    'type', ms2.signal_type,
                    'url', ms2.source_url
                ) AS signal_obj
                FROM molecule_signals ms2
                WHERE ms2.molecule_id = ms.molecule_id
                  AND ms2.source = ms.source
                ORDER BY ms2.pub_date DESC
                LIMIT 10
            ) sub
        ) AS recent_signals,
        -- Time period coverage
        MIN(pub_date)::TEXT || ' to ' || MAX(pub_date)::TEXT AS time_period
    FROM molecule_signals ms
    GROUP BY molecule_id, source
)

SELECT
    gen_random_uuid() AS id,
    molecule_id,
    source,
    sentiment_polarity,
    signal_count,
    recent_signals,
    time_period,
    NOW() AS created_at,
    NOW() AS updated_at
FROM aggregated;
