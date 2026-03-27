-- SQLMesh Model: Bronze CMS Open Payments
-- Transforms raw CMS Open Payments (physician payment) API responses to Bronze typed columns.
-- API: https://openpaymentsdata.cms.gov/api/1/datastore/query/{dataset_id}/0
-- Response shape: {"data": [{physician_npi, physician_first_name, ..., total_amount_of_payment_usdollars, ...}]}

MODEL (
    name mol_bronze.cms_open_payments,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 1000
    ),
    cron '@monthly',
    audits (
        not_null(columns := (record_id))
    ),
    grain record_id
);

WITH expanded AS (
    SELECT
        r.id              AS raw_source_id,
        r.request_timestamp,
        rec.value         AS row
    FROM mol_raw.cms_open_payments r,
         LATERAL jsonb_array_elements(
             CASE
                 WHEN r.response_body ? 'data'    THEN r.response_body->'data'
                 WHEN r.response_body ? 'results' THEN r.response_body->'results'
                 WHEN jsonb_typeof(r.response_body) = 'array' THEN r.response_body
                 ELSE '[]'::jsonb
             END
         ) AS rec(value)
    WHERE r.response_status = 200
      AND r.processed_to_bronze = FALSE
      AND r.request_timestamp BETWEEN @start_dt AND @end_dt
)

SELECT DISTINCT ON (
    COALESCE(
        row->>'record_id',
        row->>'Record_ID',
        row->>'id'
    )
)
    gen_random_uuid()                                                           AS id,

    -- Unique identifier
    COALESCE(row->>'record_id', row->>'Record_ID', row->>'id')                 AS record_id,

    -- Physician identifiers
    COALESCE(row->>'physician_npi', row->>'Physician_NPI',
             row->>'covered_recipient_npi')                                     AS physician_npi,
    COALESCE(row->>'physician_first_name', row->>'Physician_First_Name',
             row->>'covered_recipient_first_name')                              AS physician_first_name,
    COALESCE(row->>'physician_last_name', row->>'Physician_Last_Name',
             row->>'covered_recipient_last_name')                               AS physician_last_name,
    COALESCE(row->>'physician_specialty', row->>'Physician_Specialty',
             row->>'covered_recipient_specialty_1')                             AS physician_specialty,
    COALESCE(row->>'physician_state', row->>'Physician_State',
             row->>'recipient_state')                                           AS physician_state,

    -- Manufacturer / payer
    COALESCE(
        row->>'applicable_manufacturer_or_applicable_gpo_making_payment_name',
        row->>'manufacturer_name',
        row->>'Manufacturer_Name'
    )                                                                           AS manufacturer_name,

    -- Payment details
    COALESCE(
        (row->>'total_amount_of_payment_usdollars')::NUMERIC,
        (row->>'payment_amount')::NUMERIC
    )                                                                           AS payment_amount,

    COALESCE(row->>'nature_of_payment_or_transfer_of_value',
             row->>'payment_nature')                                            AS payment_nature,

    COALESCE(row->>'date_of_payment', row->>'payment_date')                    AS payment_date,

    COALESCE(
        (row->>'program_year')::INTEGER,
        (row->>'payment_year')::INTEGER
    )                                                                           AS payment_year,

    COALESCE(row->>'form_of_payment_or_transfer_of_value',
             row->>'payment_form')                                              AS payment_form,

    -- Associated drug/product (first drug slot)
    COALESCE(
        row->>'name_of_drug_or_biological_or_device_or_medical_supply_1',
        row->>'product_name',
        row->>'drug_name'
    )                                                                           AS product_name,

    -- Raw source tracking
    row                                                                         AS raw_json,
    raw_source_id,
    'cms_open_payments'                                                         AS source,
    request_timestamp                                                           AS ingested_at,
    request_timestamp,
    request_timestamp                                                           AS source_updated_at,
    FALSE                                                                       AS processed_to_silver,
    NOW()                                                                       AS created_at

FROM expanded
WHERE COALESCE(row->>'record_id', row->>'Record_ID', row->>'id') IS NOT NULL
ORDER BY
    COALESCE(row->>'record_id', row->>'Record_ID', row->>'id'),
    request_timestamp DESC NULLS LAST;
