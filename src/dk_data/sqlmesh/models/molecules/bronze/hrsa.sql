-- SQLMesh Model: Bronze HRSA Health Professional Shortage Areas
-- Transforms raw HRSA shortage area API responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration
--
-- Source: hcs_raw.hrsa_shortage_areas (envelope schema)
-- Grain: one row per hpsa_id

MODEL (
    name hcs_bronze.hrsa,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (hpsa_id)),
        unique_values(columns := (hpsa_id))
    ),
    grain hpsa_id
);

SELECT
    gen_random_uuid() AS id,

    -- HPSA identity
    response_body->>'hpsa_id'               AS hpsa_id,
    response_body->>'hpsa_name'             AS hpsa_name,

    -- Geography
    response_body->>'state'                 AS state,
    response_body->>'state_abbr'            AS state_abbr,
    response_body->>'county'                AS county,
    response_body->>'county_name'           AS county_name,

    -- Shortage classification
    response_body->>'designation_type'      AS designation_type,
    response_body->>'discipline'            AS discipline,
    response_body->>'hpsa_type'             AS hpsa_type,

    -- Status + scoring
    response_body->>'status'                AS status,
    response_body->>'hpsa_status'           AS hpsa_status,
    (response_body->>'score')::INTEGER      AS score,
    (response_body->>'hpsa_score')::INTEGER AS hpsa_score,

    -- Designation dates
    (response_body->>'designation_date')::DATE AS designation_date,

    -- Rural indicator
    response_body->>'rural_status'          AS rural_status,

    -- Raw source tracking
    response_body AS raw_json,
    id            AS raw_source_id,
    'hrsa'        AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE         AS processed_to_silver,
    NOW()         AS created_at

FROM (
    SELECT DISTINCT ON (response_body->>'hpsa_id')
        *
    FROM hcs_raw.hrsa_shortage_areas
    WHERE
        response_status = 200
        AND processed_to_bronze = FALSE
        AND response_body->>'hpsa_id' IS NOT NULL
        AND request_timestamp BETWEEN @start_dt AND @end_dt
    ORDER BY
        response_body->>'hpsa_id',
        request_timestamp DESC
) hcs_raw_hrsa_dedup;
