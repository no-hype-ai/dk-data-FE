-- SQLMesh Model: Silver CMS Hospital General Information
-- Pure 1:1 passthrough of hcs_bronze.cms_hospital_general_info per FR-001 (column
-- retention) and the project rule that bronze column names are authoritative.
--
-- This silver model exists so that the joined silvers (cms_pos, cms_chow,
-- cms_hospital_quality, cms_facility_profile) do not need to re-project
-- cms_hospital_general_info columns under prefixed alias names. Downstream
-- consumers that need the joined denormalized view should join this model with
-- the primary silver in gold.
--
-- Part of: 001-silver-medallion-rebuild (column-retention strict-mode pass)

MODEL (
    name hcs_silver.cms_hospital_general_info,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (facility_id, _source_year)
    ),
    cron '@monthly',
    audits (
        not_null(columns := (facility_id))
    ),
    grain (facility_id, _source_year)
);

SELECT
    facility_id,
    facility_name,
    address,
    city_town,
    state,
    zip_code,
    county_parish,
    telephone_number,
    hospital_type,
    hospital_ownership,
    emergency_services,
    meets_criteria_for_birthing_friendly_designation,
    hospital_overall_rating,
    hospital_overall_rating_footnote,
    _source_year,
    _source_hash,
    _source_file,
    _loaded_at
FROM hcs_bronze.cms_hospital_general_info
WHERE facility_id IS NOT NULL
