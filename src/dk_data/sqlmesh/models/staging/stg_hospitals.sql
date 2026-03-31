-- staging.hospitals - Cleaned and standardized hospital data
-- Source: hcs_raw.cms_hospital_info with deduplication, enriched with cost report bed counts
-- Model type: FULL refresh

MODEL (
    name staging.hospitals,
    kind FULL,
    cron '@daily',
    description 'Cleaned and standardized hospital master data'
);

WITH hospital_base AS (
    SELECT
        facility_id AS hospital_id,
        -- Take the most recent name for each provider
        FIRST_VALUE(facility_name) OVER (
            PARTITION BY facility_id
            ORDER BY _loaded_at DESC
        ) AS hospital_name,
        FIRST_VALUE(address) OVER (
            PARTITION BY facility_id
            ORDER BY _loaded_at DESC
        ) AS street_address,
        FIRST_VALUE(city_town) OVER (
            PARTITION BY facility_id
            ORDER BY _loaded_at DESC
        ) AS city,
        FIRST_VALUE(state) OVER (
            PARTITION BY facility_id
            ORDER BY _loaded_at DESC
        ) AS state,
        FIRST_VALUE(zip_code) OVER (
            PARTITION BY facility_id
            ORDER BY _loaded_at DESC
        ) AS zip_code,
        FIRST_VALUE(county_parish) OVER (
            PARTITION BY facility_id
            ORDER BY _loaded_at DESC
        ) AS county,
        FIRST_VALUE(hospital_type) OVER (
            PARTITION BY facility_id
            ORDER BY _loaded_at DESC
        ) AS hospital_type,
        FIRST_VALUE(hospital_ownership) OVER (
            PARTITION BY facility_id
            ORDER BY _loaded_at DESC
        ) AS ownership_type,
        FIRST_VALUE(emergency_services) OVER (
            PARTITION BY facility_id
            ORDER BY _loaded_at DESC
        ) AS has_emergency_services,
        FIRST_VALUE(hospital_overall_rating) OVER (
            PARTITION BY facility_id
            ORDER BY _loaded_at DESC
        ) AS cms_overall_rating
    FROM hcs_bronze.cms_hospital_general_info
    WHERE facility_id IS NOT NULL
      AND state IS NOT NULL
      AND LENGTH(facility_id) = 6
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY facility_id
        ORDER BY _loaded_at DESC
    ) = 1
),
-- Get most recent bed count from cost reports
cost_report_beds AS (
    SELECT
        provider_id,
        total_beds
    FROM hcs_bronze.cms_cost_reports_puf
    WHERE total_beds IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY provider_id
        ORDER BY fiscal_year_end DESC
    ) = 1
)
SELECT
    h.hospital_id,
    h.hospital_name,
    h.street_address,
    h.city,
    h.state,
    h.zip_code,
    h.county,
    -- Latitude/longitude placeholders for geocoding enrichment
    NULL::DECIMAL(9,6) AS latitude,
    NULL::DECIMAL(9,6) AS longitude,
    h.hospital_type,
    h.ownership_type,
    -- Bed count from CMS cost reports
    cr.total_beds AS bed_count,
    h.has_emergency_services,
    h.cms_overall_rating,
    -- AI enrichment fields (populated by enrichment agent)
    NULL::VARCHAR(255) AS health_system_name,
    NULL::VARCHAR(100) AS emr_system,
    NOW() AS _updated_at
FROM hospital_base h
LEFT JOIN cost_report_beds cr ON h.hospital_id = cr.provider_id;
