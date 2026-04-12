-- SQLMesh Model: Bronze Medical News
-- Transforms mol_raw.medical_news flat typed table to Bronze typed columns.
-- mol_raw.medical_news is a flat table (migration 060_ci_source_tables.sql),
-- NOT a JSONB envelope. Columns: article_id, source_name, title, summary,
-- publication_date, url, drug_mentions, therapeutic_areas, _loaded_at,
-- _source_file, _source_hash.
-- Part of: 011-datasource-integration / 015-assessment-dashboard-integration

MODEL (
    name mol_bronze.medical_news,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key article_id
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

    -- Article identifiers (flat columns — no JSON extraction needed)
    article_id::TEXT                      AS article_id,
    source_name::TEXT                     AS source_name,
    -- Strip HTML anchor tags: <a href="...">text</a> → text
    regexp_replace(title, '<[^>]+>', '', 'g')::TEXT AS title,
    summary::TEXT                         AS summary,
    -- Raw publication_date retained verbatim per FR-001; pub_date_filled is the
    -- derived column that fills missing dates from _loaded_at.
    publication_date,
    COALESCE(publication_date, _loaded_at::DATE)::DATE AS pub_date_filled,
    url::TEXT                             AS url,
    to_jsonb(drug_mentions)              AS drug_mentions,
    to_jsonb(therapeutic_areas)          AS therapeutic_areas,

    -- Raw source tracking
    NULL::TEXT                            AS raw_source_id,
    'medical_news'::TEXT                  AS source,
    _loaded_at::TIMESTAMPTZ               AS _loaded_at,
    _loaded_at::TIMESTAMPTZ               AS source_updated_at,
    FALSE                                 AS processed_to_silver,
    NOW()                                 AS created_at

FROM mol_raw.medical_news
WHERE
    title IS NOT NULL
    AND _loaded_at BETWEEN @start_dt AND @end_dt;
