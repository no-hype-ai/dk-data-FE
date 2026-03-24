-- SQLMesh Model: Bronze CMS Open Payments
-- Extracts typed columns from JSONB response_body (single table, all payment types)
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name hcs_bronze.cms_open_payments,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column ingested_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (record_id))),
    grain (record_id)
);

SELECT
    response_body->>'record_id'                             AS record_id,
    response_body->>'covered_recipient_npi'                 AS covered_recipient_npi,
    response_body->>'manufacturer_name'                     AS manufacturer_name,
    (response_body->>'total_amount_usd')::NUMERIC(12,2)     AS total_amount_usd,
    response_body->>'nature_of_payment'                     AS nature_of_payment,
    response_body->>'form_of_payment'                       AS form_of_payment,
    response_body->>'payment_type'                          AS payment_type,
    response_body->>'date_of_payment'                       AS date_of_payment,
    response_body                                           AS raw_json,
    id                                                      AS raw_source_id,
    'cms_open_payments'                                     AS source,
    ingested_at
FROM hcs_raw.cms_open_payments
WHERE response_status = 200
  AND ingested_at BETWEEN @start_dt AND @end_dt;
