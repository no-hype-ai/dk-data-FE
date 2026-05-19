-- hcs_gold.score_factors - Detailed breakdown of scoring factors
-- Source: hcs_gold.target_scores, hcs_gold.*, staging.*
-- Model type: FULL refresh

MODEL (
    name hcs_gold.score_factors,
    kind FULL,
    cron '@daily',
    description 'Detailed factor breakdown for each hospital score'
);

WITH hospital_data AS (
    -- Gather source data for factor details
    SELECT
        h.hospital_key,
        h.hospital_id,
        h.network_tier,
        h.hospital_type,
        h.ownership_type,
        h.bed_count,
        h.has_tavr_certification,
        h.state,
        sh.health_system_name,
        sh.emr_system,
        sh.has_emergency_services,
        sh.cms_overall_rating,
        g.is_hpsa_primary_care,
        g.rural_status,
        tp.estimated_total_volume AS tavr_volume,
        tp.yoy_volume_change,
        fm.operating_margin,
        fm.margin_quartile
    FROM hcs_gold.dim_hospital h
    LEFT JOIN staging.hospitals sh ON h.hospital_id = sh.hospital_id
    LEFT JOIN staging.geographic_designations g ON h.hospital_id = g.hospital_id
    LEFT JOIN hcs_gold.fact_tavr_program tp ON h.hospital_key = tp.hospital_key
        AND tp.fiscal_year = (SELECT MAX(fiscal_year) FROM hcs_gold.fact_tavr_program WHERE hospital_key = h.hospital_key)
    LEFT JOIN hcs_gold.fact_financial_metrics fm ON h.hospital_key = fm.hospital_key
        AND fm.fiscal_year = (SELECT MAX(fiscal_year) FROM hcs_gold.fact_financial_metrics WHERE hospital_key = h.hospital_key)
),
scores AS (
    SELECT
        ts.score_id,
        hd.*
    FROM hcs_gold.target_scores ts
    JOIN hospital_data hd ON ts.hospital_key = hd.hospital_key
    WHERE ts.score_date = CURRENT_DATE
)

-- Clinical Readiness Factors
SELECT
    score_id,
    'clinical_readiness' AS domain,
    'tavr_volume' AS factor_name,
    COALESCE(tavr_volume::VARCHAR, 'Unknown') AS raw_value,
    CASE
        WHEN tavr_volume >= 200 THEN 100
        WHEN tavr_volume >= 100 THEN 80
        WHEN tavr_volume >= 50 THEN 60
        WHEN tavr_volume >= 25 THEN 40
        WHEN tavr_volume > 0 THEN 20
        ELSE 0
    END AS points_awarded,
    100 AS max_points,
    CASE
        WHEN tavr_volume IS NOT NULL THEN 'verified'
        ELSE 'unknown'
    END AS confidence_level,
    'CMS Medicare Inpatient' AS data_source,
    NOW() AS _calculated_at
FROM scores

UNION ALL

SELECT
    score_id,
    'clinical_readiness' AS domain,
    'tvc_certification' AS factor_name,
    CASE WHEN has_tavr_certification THEN 'Yes' ELSE 'No' END AS raw_value,
    CASE WHEN has_tavr_certification = TRUE THEN 75 ELSE 0 END AS points_awarded,
    75 AS max_points,
    CASE
        WHEN has_tavr_certification IS NOT NULL THEN 'verified'
        ELSE 'unknown'
    END AS confidence_level,
    'ACC TVC Registry' AS data_source,
    NOW() AS _calculated_at
FROM scores

UNION ALL

SELECT
    score_id,
    'clinical_readiness' AS domain,
    'cms_quality_rating' AS factor_name,
    COALESCE(cms_overall_rating::VARCHAR, 'Unknown') AS raw_value,
    CASE
        WHEN cms_overall_rating = 5 THEN 50
        WHEN cms_overall_rating = 4 THEN 40
        WHEN cms_overall_rating = 3 THEN 30
        WHEN cms_overall_rating = 2 THEN 15
        WHEN cms_overall_rating = 1 THEN 5
        ELSE 0
    END AS points_awarded,
    50 AS max_points,
    CASE
        WHEN cms_overall_rating IS NOT NULL THEN 'verified'
        ELSE 'unknown'
    END AS confidence_level,
    'CMS Hospital Compare' AS data_source,
    NOW() AS _calculated_at
FROM scores

UNION ALL

SELECT
    score_id,
    'clinical_readiness' AS domain,
    'volume_growth' AS factor_name,
    COALESCE(ROUND(yoy_volume_change * 100, 1)::VARCHAR || '%', 'Unknown') AS raw_value,
    CASE
        WHEN yoy_volume_change > 0.20 THEN 25
        WHEN yoy_volume_change > 0.10 THEN 20
        WHEN yoy_volume_change > 0 THEN 15
        WHEN yoy_volume_change IS NULL THEN 10
        ELSE 0
    END AS points_awarded,
    25 AS max_points,
    CASE
        WHEN yoy_volume_change IS NOT NULL THEN 'high'
        ELSE 'unknown'
    END AS confidence_level,
    'CMS Medicare Inpatient' AS data_source,
    NOW() AS _calculated_at
FROM scores

-- Operational Readiness Factors
UNION ALL

SELECT
    score_id,
    'operational_readiness' AS domain,
    'bed_capacity' AS factor_name,
    COALESCE(bed_count::VARCHAR, 'Unknown') AS raw_value,
    CASE
        WHEN bed_count >= 500 THEN 100
        WHEN bed_count >= 300 THEN 80
        WHEN bed_count >= 200 THEN 60
        WHEN bed_count >= 100 THEN 40
        WHEN bed_count > 0 THEN 20
        ELSE 0
    END AS points_awarded,
    100 AS max_points,
    CASE
        WHEN bed_count IS NOT NULL THEN 'verified'
        ELSE 'unknown'
    END AS confidence_level,
    'CMS Cost Reports' AS data_source,
    NOW() AS _calculated_at
FROM scores

UNION ALL

SELECT
    score_id,
    'operational_readiness' AS domain,
    'hospital_type' AS factor_name,
    COALESCE(hospital_type, 'Unknown') AS raw_value,
    CASE
        WHEN hospital_type ILIKE '%Acute Care%' THEN 75
        WHEN hospital_type ILIKE '%Critical Access%' THEN 50
        WHEN hospital_type ILIKE '%Specialty%' THEN 40
        ELSE 25
    END AS points_awarded,
    75 AS max_points,
    'verified' AS confidence_level,
    'CMS Hospital Info' AS data_source,
    NOW() AS _calculated_at
FROM scores

UNION ALL

SELECT
    score_id,
    'operational_readiness' AS domain,
    'emergency_services' AS factor_name,
    CASE WHEN has_emergency_services = 'Yes' THEN 'Yes' ELSE 'No' END AS raw_value,
    CASE WHEN has_emergency_services = 'Yes' THEN 50 ELSE 0 END AS points_awarded,
    50 AS max_points,
    'verified' AS confidence_level,
    'CMS Hospital Info' AS data_source,
    NOW() AS _calculated_at
FROM scores

-- Strategic Alignment Factors
UNION ALL

SELECT
    score_id,
    'strategic_alignment' AS domain,
    'network_tier' AS factor_name,
    COALESCE(network_tier, 'Unknown') AS raw_value,
    CASE
        WHEN network_tier = 'Tier 1' THEN 80
        WHEN network_tier = 'Tier 2' THEN 60
        WHEN network_tier = 'Tier 3' THEN 40
        ELSE 20
    END AS points_awarded,
    80 AS max_points,
    'high' AS confidence_level,
    'Calculated' AS data_source,
    NOW() AS _calculated_at
FROM scores

UNION ALL

SELECT
    score_id,
    'strategic_alignment' AS domain,
    'market_priority' AS factor_name,
    state AS raw_value,
    CASE
        WHEN state IN ('CA', 'TX', 'FL', 'NY', 'PA') THEN 60
        WHEN state IN ('OH', 'IL', 'MI', 'GA', 'NC') THEN 50
        WHEN state IN ('AZ', 'TN', 'MO', 'WI', 'MN') THEN 40
        ELSE 30
    END AS points_awarded,
    60 AS max_points,
    'verified' AS confidence_level,
    'Market Analysis' AS data_source,
    NOW() AS _calculated_at
FROM scores

UNION ALL

SELECT
    score_id,
    'strategic_alignment' AS domain,
    'hpsa_designation' AS factor_name,
    CASE WHEN is_hpsa_primary_care THEN 'HPSA' ELSE 'Non-HPSA' END AS raw_value,
    CASE WHEN is_hpsa_primary_care = TRUE THEN 40 ELSE 0 END AS points_awarded,
    40 AS max_points,
    CASE
        WHEN is_hpsa_primary_care IS NOT NULL THEN 'verified'
        ELSE 'unknown'
    END AS confidence_level,
    'HRSA HPSA Data' AS data_source,
    NOW() AS _calculated_at
FROM scores

-- Financial Capacity Factors
UNION ALL

SELECT
    score_id,
    'financial_capacity' AS domain,
    'operating_margin' AS factor_name,
    COALESCE(ROUND(operating_margin * 100, 1)::VARCHAR || '%', 'Unknown') AS raw_value,
    CASE
        WHEN operating_margin >= 0.10 THEN 100
        WHEN operating_margin >= 0.05 THEN 80
        WHEN operating_margin >= 0.02 THEN 60
        WHEN operating_margin >= 0 THEN 40
        WHEN operating_margin IS NULL THEN 30
        ELSE 20
    END AS points_awarded,
    100 AS max_points,
    CASE
        WHEN operating_margin IS NOT NULL THEN 'verified'
        ELSE 'unknown'
    END AS confidence_level,
    'CMS Cost Reports' AS data_source,
    NOW() AS _calculated_at
FROM scores

UNION ALL

SELECT
    score_id,
    'financial_capacity' AS domain,
    'margin_quartile' AS factor_name,
    COALESCE('Q' || margin_quartile::VARCHAR, 'Unknown') AS raw_value,
    CASE
        WHEN margin_quartile = 1 THEN 50
        WHEN margin_quartile = 2 THEN 35
        WHEN margin_quartile = 3 THEN 20
        WHEN margin_quartile = 4 THEN 10
        ELSE 15
    END AS points_awarded,
    50 AS max_points,
    CASE
        WHEN margin_quartile IS NOT NULL THEN 'high'
        ELSE 'unknown'
    END AS confidence_level,
    'CMS Cost Reports' AS data_source,
    NOW() AS _calculated_at
FROM scores

-- Champion Access Factors
UNION ALL

SELECT
    score_id,
    'champion_access' AS domain,
    'health_system' AS factor_name,
    COALESCE(health_system_name, 'Independent') AS raw_value,
    CASE
        WHEN health_system_name IS NOT NULL THEN 75
        ELSE 30
    END AS points_awarded,
    75 AS max_points,
    CASE
        WHEN health_system_name IS NOT NULL THEN 'medium'
        ELSE 'low'
    END AS confidence_level,
    'AI Enrichment' AS data_source,
    NOW() AS _calculated_at
FROM scores

UNION ALL

SELECT
    score_id,
    'champion_access' AS domain,
    'emr_system' AS factor_name,
    COALESCE(emr_system, 'Unknown') AS raw_value,
    CASE
        WHEN emr_system ILIKE '%Epic%' THEN 75
        WHEN emr_system ILIKE '%Cerner%' THEN 65
        WHEN emr_system ILIKE '%Meditech%' THEN 50
        WHEN emr_system IS NOT NULL THEN 40
        ELSE 25
    END AS points_awarded,
    75 AS max_points,
    CASE
        WHEN emr_system IS NOT NULL THEN 'medium'
        ELSE 'low'
    END AS confidence_level,
    'AI Enrichment' AS data_source,
    NOW() AS _calculated_at
FROM scores;
