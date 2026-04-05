-- SQLMesh Model: Bronze Journal RSS Feeds
-- Transforms mol_raw.journal_rss flat typed table to Bronze typed columns.
-- mol_raw.journal_rss is a flat table (migration 060_ci_source_tables.sql),
-- NOT a JSONB envelope. Columns: article_id, feed_source, title, authors,
-- abstract, publication_date, link, doi, categories, _loaded_at,
-- _source_file, _source_hash.
-- Part of: 011-datasource-integration / 015-assessment-dashboard-integration

MODEL (
    name mol_bronze.journal_rss,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (article_id)),
        unique_values(columns := (article_id))
    ),
    grain article_id
);

SELECT
    gen_random_uuid()                     AS id,

    -- Entry identifiers (flat columns — no JSON extraction needed)
    article_id::TEXT                      AS article_id,
    feed_source::TEXT                     AS feed_source,
    title::TEXT                           AS title,
    authors::TEXT                         AS authors,
    abstract::TEXT                        AS abstract,
    publication_date::DATE                AS pub_date,
    link::TEXT                            AS link,
    doi::TEXT                             AS doi,
    categories::JSONB                     AS categories,

    -- Raw source tracking
    NULL::TEXT                            AS raw_source_id,
    'journal_rss'::TEXT                   AS source,
    _loaded_at::TIMESTAMPTZ               AS _loaded_at,
    _loaded_at::TIMESTAMPTZ               AS source_updated_at,
    FALSE                                 AS processed_to_silver,
    NOW()                                 AS created_at

FROM mol_raw.journal_rss
WHERE
    title IS NOT NULL
    AND _loaded_at BETWEEN @start_dt AND @end_dt;
