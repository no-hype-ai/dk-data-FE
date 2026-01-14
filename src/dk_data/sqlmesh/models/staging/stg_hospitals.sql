-- staging.hospitals - Cleaned and standardized hospital data
-- Source: raw.cms_hospital_info with deduplication
-- Model type: FULL refresh

MODEL (
    name staging.hospitals,
    kind FULL,
    cron '@daily',
    description 'Cleaned and standardized hospital master data'
);

SELECT
    provider_id AS hospital_id,
    -- Take the most recent name for each provider
    FIRST_VALUE(hospital_name) OVER (
        PARTITION BY provider_id
        ORDER BY _loaded_at DESC
    ) AS hospital_name,
    FIRST_VALUE(address) OVER (
        PARTITION BY provider_id
        ORDER BY _loaded_at DESC
    ) AS street_address,
    FIRST_VALUE(city) OVER (
        PARTITION BY provider_id
        ORDER BY _loaded_at DESC
    ) AS city,
    FIRST_VALUE(state) OVER (
        PARTITION BY provider_id
        ORDER BY _loaded_at DESC
    ) AS state,
    FIRST_VALUE(zip_code) OVER (
        PARTITION BY provider_id
        ORDER BY _loaded_at DESC
    ) AS zip_code,
    FIRST_VALUE(county_name) OVER (
        PARTITION BY provider_id
        ORDER BY _loaded_at DESC
    ) AS county,
    -- Latitude/longitude placeholders for geocoding enrichment
    NULL::DECIMAL(9,6) AS latitude,
    NULL::DECIMAL(9,6) AS longitude,
    FIRST_VALUE(hospital_type) OVER (
        PARTITION BY provider_id
        ORDER BY _loaded_at DESC
    ) AS hospital_type,
    FIRST_VALUE(hospital_ownership) OVER (
        PARTITION BY provider_id
        ORDER BY _loaded_at DESC
    ) AS ownership_type,
    -- Bed count from cost reports (joined later or enriched)
    NULL::INTEGER AS bed_count,
    FIRST_VALUE(emergency_services) OVER (
        PARTITION BY provider_id
        ORDER BY _loaded_at DESC
    ) AS has_emergency_services,
    FIRST_VALUE(hospital_overall_rating) OVER (
        PARTITION BY provider_id
        ORDER BY _loaded_at DESC
    ) AS cms_overall_rating,
    -- AI enrichment fields (populated by enrichment agent)
    NULL::VARCHAR(255) AS health_system_name,
    NULL::VARCHAR(100) AS emr_system,
    NOW() AS _updated_at
FROM raw.cms_hospital_info
WHERE provider_id IS NOT NULL
  AND state IS NOT NULL
  AND LENGTH(provider_id) = 6
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY provider_id
    ORDER BY _loaded_at DESC
) = 1;
