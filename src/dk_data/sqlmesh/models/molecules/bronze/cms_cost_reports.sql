-- SQLMesh Model: Bronze CMS Cost Reports
-- Transforms flat hcs_raw.cms_cost_reports typed columns to Bronze canonical schema
-- Part of: 015-assessment-dashboard-integration
--
-- Source: hcs_raw.cms_cost_reports (flat typed columns, populated by load_cms_cost_reports)
-- Grain: one row per (provider_id, fiscal_year_begin)

MODEL (
    name hcs_bronze.cms_cost_reports,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (provider_id, fiscal_year_begin)
    ),
    cron '@daily',
    audits (
        not_null(columns := (provider_id)),
        unique_values(columns := (provider_id, fiscal_year_begin))
    ),
    grain provider_id
);

SELECT
    gen_random_uuid() AS id,

    -- Provider identity
    r.provider_id::TEXT                     AS provider_id,
    r.provider_name::TEXT                   AS provider_name,
    r.provider_state::TEXT                  AS provider_state,

    -- Fiscal period
    r.fiscal_year_begin::DATE               AS fiscal_year_begin,
    r.fiscal_year_end::DATE                 AS fiscal_year_end,

    -- Financial metrics
    r.net_patient_revenue::NUMERIC          AS net_patient_revenue,
    r.total_operating_expenses::NUMERIC     AS total_operating_expenses,
    (
        CASE
            WHEN r.total_operating_expenses > 0
            THEN (r.net_patient_revenue - r.total_operating_expenses)
                 / r.total_operating_expenses
            ELSE NULL
        END
    )::NUMERIC(8,4)                         AS operating_margin,

    -- Capacity
    r.bed_count::INTEGER                    AS bed_count,

    -- Source tracking
    'cms_cost_reports'                      AS source,
    r._loaded_at                            AS source_updated_at,
    FALSE                                   AS processed_to_silver,
    NOW()                                   AS created_at

FROM hcs_raw.cms_cost_reports r
WHERE
    r.provider_id IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;
