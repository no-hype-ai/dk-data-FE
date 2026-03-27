-- SQLMesh Model: Bronze CMS NDC Directory
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_ndc,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (product_ndc))),
    grain (product_ndc)
);

SELECT
    COALESCE(
        response_body->>'product_ndc',
        response_body->>'ndc'
    )                                   AS product_ndc,
    response_body->>'proprietary_name'  AS proprietary_name,
    response_body->>'nonproprietary_name' AS nonproprietary_name,
    response_body->>'labeler_name'      AS labeler_name,
    response_body->>'dosage_form'       AS dosage_form,
    response_body->>'route'             AS route,
    response_body->>'product_type'      AS product_type,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_ndc'                           AS source,
    ingested_at
FROM hcs_raw.cms_ndc
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
