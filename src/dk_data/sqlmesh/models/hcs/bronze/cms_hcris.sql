-- SQLMesh Model: Bronze CMS HCRIS (Hospital Cost Report Information System)
-- Extracts typed columns from JSONB response_body (one row per worksheet line)
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_hcris,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (ccn, worksheet, line_number, column_number)
    ),
    cron '@daily',
    audits (not_null(columns := (ccn))),
    grain (ccn, worksheet, line_number, column_number)
);

SELECT
    response_body->>'ccn'               AS ccn,
    response_body->>'fiscal_year_begin' AS fiscal_year_begin,
    response_body->>'fiscal_year_end'   AS fiscal_year_end,
    response_body->>'worksheet'         AS worksheet,
    response_body->>'line_number'       AS line_number,
    response_body->>'column_number'     AS column_number,
    (response_body->>'value')::NUMERIC  AS value,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_hcris'                         AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_hcris
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
