-- SQLMesh Model: Bronze CMS Outpatient PUF
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_outpatient_puf,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (ccn, apc_code))),
    grain (ccn, apc_code)
);

SELECT
    response_body->>'ccn'                                   AS ccn,
    response_body->>'apc_code'                              AS apc_code,
    response_body->>'apc_description'                       AS apc_description,
    (response_body->>'total_services')::INTEGER             AS total_services,
    (response_body->>'avg_submitted_charges')::NUMERIC(12,2) AS avg_submitted_charges,
    (response_body->>'avg_total_payments')::NUMERIC(12,2)   AS avg_total_payments,
    response_body                                           AS raw_json,
    id                                                      AS raw_source_id,
    'cms_outpatient_puf'                                    AS source,
    ingested_at
FROM hcs_raw.cms_outpatient_puf
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
