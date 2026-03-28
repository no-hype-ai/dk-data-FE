-- SQLMesh Model: Bronze HRSA Shortage Areas
-- Transforms flat hcs_raw.hrsa_shortage_areas table to Bronze typed columns.
-- Source: hcs_raw.hrsa_shortage_areas (flat table, migration 105)
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name hcs_bronze.hrsa,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (hpsa_id))
    ),
    grain hpsa_id
);

SELECT
    gen_random_uuid() AS id,

    -- HPSA identifiers
    hpsa_id::TEXT AS hpsa_id,
    hpsa_name::TEXT AS hpsa_name,
    designation_type::TEXT AS designation_type,
    state_abbr::TEXT AS state,
    county_name::TEXT AS county,
    hpsa_type::TEXT AS discipline,
    hpsa_score::INTEGER AS score,
    hpsa_status::TEXT AS status,

    -- Raw source tracking
    id::BIGINT AS raw_source_id,
    'hrsa_shortage_areas' AS source,
    _fetched_at AS request_timestamp,
    _fetched_at AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM hcs_raw.hrsa_shortage_areas
WHERE
    hpsa_id IS NOT NULL
    AND _fetched_at BETWEEN @start_dt AND @end_dt;
