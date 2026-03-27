-- SQLMesh Model: Bronze CMS Cost Reports
-- Transforms raw CMS Hospital Cost Report (HCRIS) data to Bronze typed columns
-- Source: hcs_raw.cms_cost_reports (flat typed table, loaded by cms_cost_reports.py)
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name hcs_bronze.cms_cost_reports,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (provider_id, fiscal_year_end)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (provider_id))
    ),
    grain (provider_id, fiscal_year_end)
);

SELECT
    gen_random_uuid() AS id,

    -- Record identifier: provider_id + fiscal year end (TEXT, always)
    r.provider_id::TEXT AS provider_id,

    -- Fiscal period (DATE columns in raw table)
    r.fiscal_year_begin::DATE AS fiscal_year_begin,
    r.fiscal_year_end::DATE AS fiscal_year_end,

    -- Capacity metrics (INTEGER)
    r.total_beds::INTEGER AS bed_count,
    r.total_discharges::INTEGER AS total_discharges,

    -- Financial metrics (NUMERIC — raw table uses DECIMAL(15,2))
    r.net_patient_revenue::NUMERIC AS net_patient_revenue,
    r.total_operating_expenses::NUMERIC AS total_operating_expenses,
    r.operating_margin::NUMERIC AS operating_margin,

    -- Source tracking
    r._source_hash AS source_hash,
    r._loaded_at AS source_updated_at,
    'cms_cost_reports' AS source,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM hcs_raw.cms_cost_reports r
WHERE
    r.provider_id IS NOT NULL
    AND r._loaded_at BETWEEN @start_dt AND @end_dt;
