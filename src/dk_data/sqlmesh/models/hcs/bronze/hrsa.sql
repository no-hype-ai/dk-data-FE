-- SQLMesh Model: Bronze HRSA Shortage Areas
-- Transforms flat hcs_raw.hrsa_shortage_areas table to Bronze typed columns.
-- Source: hcs_raw.hrsa_shortage_areas (flat table, migration 105)
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name hcs_bronze.hrsa,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key hpsa_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (hpsa_id))
    ),
    grain hpsa_id
);

SELECT
    gen_random_uuid() AS id,

    -- HPSA identifiers (raw column names preserved for bronze completeness)
    hpsa_id::TEXT AS hpsa_id,
    hpsa_name::TEXT AS hpsa_name,
    hpsa_type::TEXT AS hpsa_type,
    designation_type::TEXT AS designation_type,
    state_abbr::TEXT AS state_abbr,
    county_name::TEXT AS county_name,
    hpsa_score::INTEGER AS hpsa_score,
    designation_date::DATE AS designation_date,
    rural_status::TEXT AS rural_status,

    -- Aliased for downstream silver compatibility
    state_abbr::TEXT AS state,
    county_name::TEXT AS county,
    hpsa_type::TEXT AS discipline,
    hpsa_score::INTEGER AS score,
    rural_status::TEXT AS status,

    -- Item 27d: HRSA expansion columns
    hpsa_status_code,
    designation_history,
    provider_count,
    primary_care_physician_count,
    dental_provider_count,
    mental_health_provider_count,
    mua_status,
    mua_score,
    withdrawn_date,

    -- Raw source tracking
    id::BIGINT AS raw_source_id,
    'hrsa_shortage_areas' AS source,
    _source_hash::TEXT AS _source_hash,
    _fetched_at::TIMESTAMPTZ AS _fetched_at,
    _fetched_at::TIMESTAMPTZ AS request_timestamp,
    _fetched_at::TIMESTAMPTZ AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM hcs_raw.hrsa_shortage_areas
WHERE
    hpsa_id IS NOT NULL
    AND _fetched_at BETWEEN @start_dt AND @end_dt;
