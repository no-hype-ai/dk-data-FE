-- SQLMesh Model: Bronze ACC TAVR Certification (TVC)
-- Transforms raw ACC TVC certification API responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration
--
-- Source: hcs_raw.acc_tvc_certification (envelope schema)
-- Grain: one row per facility_id

MODEL (
    name hcs_bronze.acc_tvc,
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

    -- Facility identity
    response_body->>'facility_id'           AS facility_id,
    response_body->>'facility_name'         AS facility_name,
    response_body->>'city'                  AS city,
    response_body->>'state'                 AS state,
    response_body->>'zip_code'              AS zip_code,

    -- Certification details
    response_body->>'certification_type'    AS certification_type,
    (response_body->>'cert_date')::DATE     AS cert_date,
    (response_body->>'expiry_date')::DATE   AS expiry_date,
    response_body->>'cert_status'           AS cert_status,

    -- Volume metrics
    (response_body->>'volumes')::INTEGER    AS volumes,
    (response_body->>'annual_case_volume')::INTEGER AS annual_case_volume,

    -- Raw source tracking
    response_body AS raw_json,
    id            AS raw_source_id,
    'acc_tvc'     AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE         AS processed_to_silver,
    NOW()         AS created_at

FROM (
    SELECT DISTINCT ON (response_body->>'facility_id')
        *
    FROM hcs_raw.acc_tvc_certification
    WHERE
        response_status = 200
        AND processed_to_bronze = FALSE
        AND response_body->>'facility_id' IS NOT NULL
        AND request_timestamp BETWEEN @start_dt AND @end_dt
    ORDER BY
        response_body->>'facility_id',
        request_timestamp DESC
) hcs_raw_acc_tvc_dedup;
