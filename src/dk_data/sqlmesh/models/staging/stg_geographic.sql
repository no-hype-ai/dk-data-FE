-- staging.geographic_designations - HPSA and geographic designations by hospital
-- Source: raw.hrsa_shortage_areas, hcs_raw.cms_hospital_info
-- Model type: FULL refresh

MODEL (
    name staging.geographic_designations,
    kind FULL,
    cron '@daily',
    description 'Geographic and shortage area designations for hospitals'
);

WITH hospital_counties AS (
    -- Get unique hospital-county combinations
    SELECT DISTINCT
        provider_id AS hospital_id,
        state,
        county_name
    FROM hcs_raw.cms_hospital_info
    WHERE provider_id IS NOT NULL
      AND county_name IS NOT NULL
),
hpsa_by_county AS (
    -- Aggregate HPSA designations by state/county
    -- HRSA county_name format: "Macon County, AL" - extract just "Macon"
    SELECT
        state_abbr,
        -- Normalize county name: extract part before " County" or use as-is
        UPPER(TRIM(
            CASE
                WHEN county_name LIKE '% County,%' THEN SPLIT_PART(county_name, ' County,', 1)
                WHEN county_name LIKE '% County' THEN SPLIT_PART(county_name, ' County', 1)
                ELSE county_name
            END
        )) AS county_name_normalized,
        -- Primary Care HPSA
        BOOL_OR(hpsa_type = 'Primary Care') AS is_hpsa_primary_care,
        -- Mental Health HPSA
        BOOL_OR(hpsa_type = 'Mental Health') AS is_hpsa_mental_health,
        -- Max HPSA score for the county
        MAX(hpsa_score) AS hpsa_score,
        -- Rural status (take most common)
        MODE() WITHIN GROUP (ORDER BY rural_status) AS rural_status
    FROM raw.hrsa_shortage_areas
    WHERE state_abbr IS NOT NULL
      AND county_name IS NOT NULL
      AND county_name != ''
    GROUP BY state_abbr, county_name_normalized
)
SELECT
    h.hospital_id,
    COALESCE(hp.is_hpsa_primary_care, FALSE) AS is_hpsa_primary_care,
    COALESCE(hp.is_hpsa_mental_health, FALSE) AS is_hpsa_mental_health,
    -- MUA (Medically Underserved Area) - placeholder for future data source
    NULL::BOOLEAN AS is_mua,
    hp.hpsa_score,
    hp.rural_status,
    NOW() AS _updated_at
FROM hospital_counties h
LEFT JOIN hpsa_by_county hp ON (
    UPPER(h.state) = UPPER(hp.state_abbr)
    AND UPPER(h.county_name) = hp.county_name_normalized
);
