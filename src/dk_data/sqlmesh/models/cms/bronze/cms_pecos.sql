-- SQLMesh Model: Bronze CMS PECOS Provider Enrollment
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_pecos,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (enrollment_id))),
    grain (enrollment_id)
);

SELECT
    response_body->>'enrollment_id'     AS enrollment_id,
    response_body->>'npi'               AS npi,
    response_body->>'organization_name' AS organization_name,
    response_body->>'enrollment_type'   AS enrollment_type,
    response_body->>'state'             AS enrollment_state,
    response_body->>'first_name'        AS first_name,
    response_body->>'last_name'         AS last_name,
    response_body                       AS raw_json,
    id                                  AS raw_source_id,
    'cms_pecos'                         AS source,
    ingested_at
FROM hcs_raw.cms_pecos
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
