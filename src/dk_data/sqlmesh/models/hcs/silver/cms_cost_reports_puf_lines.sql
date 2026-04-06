-- SQLMesh Model: Silver CMS Cost Reports PUF — Worksheet-Level Staffing Lines
-- Typed pass-through from hcs_bronze.cms_cost_reports_puf_lines with facility enrichment.
-- Grain: (provider_id, line_item_code, _source_year)
-- Linkage: provider_id → hcs_bronze.cms_hospital_general_info (most recent year via DISTINCT ON)

MODEL (
    name hcs_silver.cms_cost_reports_puf_lines,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (provider_id, line_item_code, _source_year))
    ),
    grain (provider_id, line_item_code, _source_year)
);

SELECT DISTINCT ON (b.provider_id, b.line_item_code, b._source_year)
    gen_random_uuid()           AS id,
    b.provider_id,
    b.line_item_code,
    b.line_item_description,
    b.reported_hours_fte,
    b.total_salaries,
    b.facility_type,
    b.source_year,
    b._source_year,
    b._source_hash,

    -- Facility enrichment from hospital general info (most recent year)
    h.facility_name,
    h.address                   AS facility_address,
    h.city_town                 AS facility_city,
    h.state                     AS facility_state,
    h.zip_code                  AS facility_zip_code,
    h.county_parish,
    h.telephone_number,
    h.hospital_type,
    h.hospital_ownership,
    h.emergency_services,
    h.meets_criteria_for_birthing_friendly_designation,
    h.hospital_overall_rating,
    h.hospital_overall_rating_footnote,

    'cms_cost_reports_puf_lines' AS source,
    b._source_file,
    b._loaded_at                AS source_updated_at,
    NOW()                       AS created_at

FROM hcs_bronze.cms_cost_reports_puf_lines b
LEFT JOIN hcs_bronze.cms_hospital_general_info h
       ON b.provider_id = h.facility_id

WHERE b.provider_id IS NOT NULL
  AND b.line_item_code IS NOT NULL
ORDER BY b.provider_id, b.line_item_code, b._source_year, h._source_year DESC NULLS LAST
