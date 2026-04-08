-- SQLMesh Model: Bronze CMS USP Drug Classification
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_usp,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key rxcui
    ),
    cron '@daily',
    audits (not_null(columns := (rxcui))),
    grain (rxcui)
);

SELECT
    response_body->>'rxcui'             AS rxcui,
    response_body->>'tty'               AS tty,
    response_body->>'branded_name'      AS branded_name,
    response_body->>'usp_category'      AS usp_category,
    response_body->>'usp_class'         AS usp_class,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_usp'                           AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_usp
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
