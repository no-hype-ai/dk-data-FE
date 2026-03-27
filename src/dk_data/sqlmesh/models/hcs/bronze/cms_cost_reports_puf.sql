-- SQLMesh Model: Bronze CMS Hospital Cost Reports PUF
-- Typed pass-through from hcs_raw.cms_cost_reports_puf
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_cost_reports_puf,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (provider_id, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (provider_id, _source_year))
    ),
    grain (provider_id, _source_year)
);

SELECT
    id,
    provider_id,
    hospital_name,
    city,
    state,
    zip_code,
    fiscal_year_begin,
    fiscal_year_end,
    total_beds,
    total_discharges,
    net_patient_revenue,
    total_operating_expenses,
    operating_margin,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_cost_reports_puf;
