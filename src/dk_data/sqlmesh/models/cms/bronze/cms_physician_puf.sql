-- SQLMesh Model: Bronze CMS Physician & Other Practitioners PUF
-- Extracts typed columns from JSONB response_body
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_physician_puf,
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
    response_body->>'hcpcs_description'                         AS hcpcs_description,
    response_body->>'provider_type'                             AS provider_type,
    response_body->>'place_of_service'                          AS place_of_service,
    response_body->>'nppes_provider_last_org_name'              AS provider_last_org_name,
    response_body->>'nppes_provider_first_name'                 AS provider_first_name,
    response_body->>'nppes_provider_state'                      AS provider_state,
    (response_body->>'line_srvc_cnt')::NUMERIC                  AS line_srvc_cnt,
    (response_body->>'bene_unique_cnt')::INTEGER                AS bene_unique_cnt,
    (response_body->>'average_medicare_payment_amt')::NUMERIC(12,2) AS avg_medicare_payment_amt,
    (response_body->>'average_medicare_allowed_amt')::NUMERIC(12,2) AS avg_medicare_allowed_amt,
    response_body                                               AS raw_json,
    id                                                          AS raw_source_id,
    'cms_physician_puf'                                         AS source,
    ingested_at
FROM hcs_raw.cms_physician_puf
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
