-- SQLMesh Model: Bronze CMS Inpatient PUF
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_inpatient_puf,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (ccn, drg_code))),
    grain (ccn, drg_code)
);

SELECT
    response_body->>'ccn'                               AS ccn,
    response_body->>'drg_code'                          AS drg_code,
    response_body->>'drg_description'                   AS drg_description,
    (response_body->>'total_discharges')::INTEGER       AS total_discharges,
    (response_body->>'avg_covered_charges')::NUMERIC    AS avg_covered_charges,
    (response_body->>'avg_total_payments')::NUMERIC     AS avg_total_payments,
    (response_body->>'avg_medicare_payments')::NUMERIC  AS avg_medicare_payments,
    response_body                                       AS raw_json,
    id                                                  AS raw_source_id,
    'cms_inpatient_puf'                                 AS source,
    ingested_at
FROM hcs_raw.cms_inpatient_puf
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
