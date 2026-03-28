-- SQLMesh Model: Bronze CMS RBCS Classification
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_rbcs,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (hcpcs_code))),
    grain (hcpcs_code)
);

SELECT
    response_body->>'hcpcs_code'        AS hcpcs_code,
    response_body->>'rbcs_id'           AS rbcs_id,
    response_body->>'rbcs_category'     AS rbcs_category,
    response_body->>'rbcs_subcategory'  AS rbcs_subcategory,
    response_body->>'rbcs_family'       AS rbcs_family,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_rbcs'                          AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_rbcs
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
