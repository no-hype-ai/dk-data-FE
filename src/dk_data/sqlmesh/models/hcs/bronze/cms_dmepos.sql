-- SQLMesh Model: Bronze CMS DMEPOS Utilization
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_dmepos,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (npi, hcpcs_code))),
    grain (npi, hcpcs_code)
);

SELECT
    response_body->>'npi'                                       AS npi,
    response_body->>'hcpcs_code'                                AS hcpcs_code,
    (response_body->>'total_services')::INTEGER                 AS total_services,
    (response_body->>'total_beneficiaries')::INTEGER            AS total_beneficiaries,
    (response_body->>'avg_submitted_charge')::NUMERIC             AS avg_submitted_charge,
    (response_body->>'avg_medicare_payment')::NUMERIC             AS avg_medicare_payment,
    response_body                                               AS raw_json,
    id                                                          AS raw_source_id,
    'cms_dmepos'                                                AS source,
    FALSE AS processed_to_silver,
    ingested_at
FROM hcs_raw.cms_dmepos
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
