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

-- mol_silver.news_signals is populated by ip_silver pipeline (not yet run).
-- Return empty result set with correct schema until ip_silver runs.
SELECT
    gen_random_uuid() AS id,
    NULL::UUID AS molecule_id,
    NULL::TEXT AS source,
    NULL::TEXT AS sentiment_polarity,
    0 AS signal_count,
    NULL::JSONB AS recent_signals,
    NULL::TEXT AS time_period,
    NOW() AS created_at,
    NOW() AS updated_at
WHERE FALSE;
