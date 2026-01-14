-- mart.dim_hospital - Hospital dimension with SCD Type 2
-- Source: staging.hospitals, staging.certifications
-- Model type: SCD Type 2

MODEL (
    name mart.dim_hospital,
    kind FULL,
    cron '@daily',
    description 'Hospital dimension table'
);

SELECT
    h.hospital_id,
    h.hospital_id AS hospital_key,  -- For foreign key references
    h.hospital_name,
    h.health_system_name,
    -- Network tier based on bed count and TAVR volume
    CASE
        WHEN h.bed_count >= 500 THEN 'Tier 1'
        WHEN h.bed_count >= 300 THEN 'Tier 2'
        WHEN h.bed_count >= 150 THEN 'Tier 3'
        ELSE 'Tier 4'
    END AS network_tier,
    h.state,
    h.city,
    h.county,
    h.hospital_type,
    h.ownership_type,
    h.bed_count,
    -- Check if hospital has active TVC certification
    CASE
        WHEN c.is_active = TRUE THEN TRUE
        ELSE FALSE
    END AS has_tavr_certification,
    NOW() AS _updated_at
FROM staging.hospitals h
LEFT JOIN staging.certifications c ON h.hospital_id = c.hospital_id
    AND c.certification_type LIKE '%Transcatheter%'
    AND c.is_active = TRUE
-- Deduplicate in case of multiple certifications
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY h.hospital_id
    ORDER BY c.certification_date DESC NULLS LAST
) = 1;
