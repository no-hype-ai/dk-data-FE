-- SQLMesh Model: Bronze CMS HCRIS
-- Normalizes raw Healthcare Cost Report Information System data to typed Bronze columns
-- Part of: 016-cms-puf-datasource-integration (Phase 3 — Facility MVP)

MODEL (
    name bronze.cms_hcris,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column _loaded_at,
        batch_size 500
    ),
    cron '@daily',
    audits (not_null(columns := (report_id))),
    grain (report_id)
);

SELECT
    TRIM(report_id)::TEXT                       AS report_id,
    TRIM(provider_ccn)::TEXT                    AS provider_ccn,
    fiscal_year_begin::DATE                     AS fiscal_year_begin,
    fiscal_year_end::DATE                       AS fiscal_year_end,
    total_costs::NUMERIC                        AS total_costs,
    total_revenue::NUMERIC                      AS total_revenue,
    net_income::NUMERIC                         AS net_income,
    _loaded_at,
    _source_file,
    _source_hash
FROM hcs_raw.cms_hcris
WHERE _loaded_at BETWEEN @start_dt AND @end_dt;
