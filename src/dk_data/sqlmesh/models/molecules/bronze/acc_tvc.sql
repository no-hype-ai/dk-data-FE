-- SQLMesh Model: Bronze ACC/TVC Certification
-- Transforms raw ACC/TVC certification data to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_bronze.acc_tvc,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (facility_id)),
        unique_values(columns := (facility_id))
    ),
    grain facility_id
);

SELECT
    gen_random_uuid() AS id,

    -- Facility identifiers
    response_body->>'facility_id' AS facility_id,
    response_body->>'facility_name' AS facility_name,
    response_body->>'city' AS city,
    response_body->>'state' AS state,
    response_body->>'certification_type' AS certification_type,
    response_body->>'cert_date' AS cert_date,
    response_body->'volumes' AS volumes,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'acc_tvc' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.acc_tvc_certification
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'facility_id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
