-- SQLMesh Model: Bronze CMS NUCC Provider Taxonomy
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_nucc,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (taxonomy_code))),
    grain (taxonomy_code)
);

SELECT
    response_body->>'taxonomy_code'     AS taxonomy_code,
    response_body->>'taxonomy_type'     AS taxonomy_type,
    response_body->>'classification'    AS classification,
    response_body->>'specialization'    AS specialization,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_nucc'                          AS source,
    ingested_at
FROM hcs_raw.cms_nucc
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
