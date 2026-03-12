-- SQLMesh Model: Bronze CMS Post-Acute Care
-- Normalizes raw Post-Acute Care PUF to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name bronze.cms_post_acute,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (provider_id))),
    grain (provider_id)
);

SELECT
    TRIM(provider_id)::TEXT                     AS provider_id,
    UPPER(TRIM(provider_type))                  AS provider_type,
    COALESCE(total_episodes, 0)::INTEGER        AS total_episodes,
    COALESCE(avg_spending_per_episode, 0)::NUMERIC(10,2) AS avg_spending_per_episode,
    year::INTEGER                               AS year,
    _loaded_at,
    _source_file,
    _source_hash
FROM raw.cms_post_acute
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
