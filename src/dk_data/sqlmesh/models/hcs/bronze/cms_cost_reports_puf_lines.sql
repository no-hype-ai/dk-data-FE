-- SQLMesh Model: Bronze CMS Cost Reports PUF — Worksheet-Level Staffing Lines
-- Typed pass-through from hcs_raw.cms_cost_reports_puf_lines
-- Feature: 019-cms-puf-platform-reconciliation

MODEL (
    name hcs_bronze.cms_cost_reports_puf_lines,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (provider_id, line_item_code, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (provider_id, line_item_code, _source_year))
    ),
    grain (provider_id, line_item_code, _source_year)
);

SELECT
    id,
    provider_id,
    line_item_code,
    line_item_description,
    reported_hours_fte,
    total_salaries,
    facility_type,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at,
    FALSE AS processed_to_silver,
    NOW() AS _bronze_loaded_at
FROM hcs_raw.cms_cost_reports_puf_lines;
