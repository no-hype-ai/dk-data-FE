-- SQLMesh Model: Bronze CMS Hospital Info
-- Transforms raw CMS Hospital Compare data to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_bronze.cms_hospital_info,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (provider_id)),
        unique_values(columns := (provider_id))
    ),
    grain provider_id
);

SELECT
    gen_random_uuid() AS id,

    -- Hospital identifiers
    provider_id,
    hospital_name,
    city,
    state,
    hospital_type,
    hospital_ownership                          AS ownership,
    hospital_overall_rating                     AS rating,

    -- Raw source tracking
    NULL::JSONB                                 AS raw_json,
    id::TEXT                                    AS raw_source_id,
    'cms_hospital_info'                         AS source,
    _loaded_at,
    _loaded_at                                  AS source_updated_at,
    FALSE                                       AS processed_to_silver,
    NOW()                                       AS created_at

FROM hcs_raw.cms_hospital_info
WHERE
    provider_id IS NOT NULL
    AND _loaded_at BETWEEN @start_dt AND @end_dt;
