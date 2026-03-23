-- SQLMesh Model: Bronze CMS Cost Reports
-- Transforms raw CMS Hospital Cost Report data to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name mol_bronze.cms_cost_reports,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (provider_id)),
        unique_values(columns := (record_id))
    ),
    grain record_id
);

SELECT
    gen_random_uuid() AS id,

    -- Record identifiers
    provider_id || '_' || fiscal_year_end::TEXT AS record_id,
    provider_id,
    fiscal_year_end::TEXT                       AS fiscal_year,
    total_operating_expenses                    AS total_costs,
    net_patient_revenue                         AS net_revenue,
    operating_margin,
    total_beds                                  AS bed_count,

    -- Raw source tracking
    NULL::JSONB                                 AS raw_json,
    id::TEXT                                    AS raw_source_id,
    'cms_cost_reports'                          AS source,
    _loaded_at,
    _loaded_at                                  AS source_updated_at,
    FALSE                                       AS processed_to_silver,
    NOW()                                       AS created_at

FROM hcs_raw.cms_cost_reports
WHERE
    provider_id IS NOT NULL
    AND _loaded_at BETWEEN @start_dt AND @end_dt;
