-- scoring.target_scores - Target Readiness Score calculations
-- Source: mart.dim_hospital, mart.fact_tavr_program, mart.fact_financial_metrics,
--         hcs_silver.geographic_designations, staging.hospitals
-- Model type: FULL refresh

MODEL (
    name scoring.target_scores,
    kind FULL,
    cron '@daily',
    description 'Target Readiness Scores across five domains with tier classification'
);

WITH hospital_data AS (
    -- Gather all data needed for scoring from various sources
    SELECT
        h.hospital_key,
        h.hospital_id,
        h.hospital_name,
        h.state,
        h.network_tier,
        h.hospital_type,
        h.ownership_type,
        h.bed_count,
        h.has_tavr_certification,
        -- From staging for enrichment data
        sh.health_system_name,
        sh.emr_system,
        sh.has_emergency_services,
        sh.cms_overall_rating,
        -- Geographic data
        g.is_hpsa_primary_care,
        g.rural_status,
        -- Latest TAVR program metrics
        tp.estimated_total_volume AS tavr_volume,
        tp.yoy_volume_change,
        -- Financial metrics
        fm.operating_margin,
        fm.margin_quartile
    FROM mart.dim_hospital h
    LEFT JOIN staging.hospitals sh ON h.hospital_id = sh.hospital_id
    LEFT JOIN hcs_silver.geographic_designations g ON h.hospital_id = g.hospital_id
    LEFT JOIN mart.fact_tavr_program tp ON h.hospital_key = tp.hospital_key
        AND tp.fiscal_year = (
            SELECT MAX(fiscal_year)
            FROM mart.fact_tavr_program
            WHERE hospital_key = h.hospital_key
        )
    LEFT JOIN mart.fact_financial_metrics fm ON h.hospital_key = fm.hospital_key
        AND fm.fiscal_year = (
            SELECT MAX(fiscal_year)
            FROM mart.fact_financial_metrics
            WHERE hospital_key = h.hospital_key
        )
),
scored AS (
    SELECT
        hospital_key,

        -- Clinical Readiness Score (max 250)
        LEAST(250, (
            -- Volume points (0-100)
            CASE
                WHEN tavr_volume >= 200 THEN 100
                WHEN tavr_volume >= 100 THEN 80
                WHEN tavr_volume >= 50 THEN 60
                WHEN tavr_volume >= 25 THEN 40
                WHEN tavr_volume > 0 THEN 20
                ELSE 0
            END
            -- Certification points (0-75)
            + CASE WHEN has_tavr_certification = TRUE THEN 75 ELSE 0 END
            -- Quality rating points (0-50)
            + CASE
                WHEN cms_overall_rating = 5 THEN 50
                WHEN cms_overall_rating = 4 THEN 40
                WHEN cms_overall_rating = 3 THEN 30
                WHEN cms_overall_rating = 2 THEN 15
                WHEN cms_overall_rating = 1 THEN 5
                ELSE 0
            END
            -- Growth trajectory (0-25)
            + CASE
                WHEN yoy_volume_change > 0.20 THEN 25
                WHEN yoy_volume_change > 0.10 THEN 20
                WHEN yoy_volume_change > 0 THEN 15
                WHEN yoy_volume_change IS NULL THEN 10
                ELSE 0
            END
        )) AS clinical_readiness_score,

        -- Operational Readiness Score (max 250)
        LEAST(250, (
            -- Bed capacity points (0-100)
            CASE
                WHEN bed_count >= 500 THEN 100
                WHEN bed_count >= 300 THEN 80
                WHEN bed_count >= 200 THEN 60
                WHEN bed_count >= 100 THEN 40
                WHEN bed_count > 0 THEN 20
                ELSE 0
            END
            -- Hospital type points (0-75)
            + CASE
                WHEN hospital_type ILIKE '%Acute Care%' THEN 75
                WHEN hospital_type ILIKE '%Critical Access%' THEN 50
                WHEN hospital_type ILIKE '%Specialty%' THEN 40
                ELSE 25
            END
            -- Emergency services points (0-50)
            + CASE WHEN has_emergency_services = TRUE THEN 50 ELSE 0 END
            -- Ownership type points (0-25)
            + CASE
                WHEN ownership_type ILIKE '%Government%' THEN 25
                WHEN ownership_type ILIKE '%Voluntary%' THEN 20
                WHEN ownership_type ILIKE '%Proprietary%' THEN 15
                ELSE 10
            END
        )) AS operational_readiness_score,

        -- Strategic Alignment Score (max 200)
        LEAST(200, (
            -- Network tier points (0-80)
            CASE
                WHEN network_tier = 'Tier 1' THEN 80
                WHEN network_tier = 'Tier 2' THEN 60
                WHEN network_tier = 'Tier 3' THEN 40
                ELSE 20
            END
            -- Market priority (0-60)
            + CASE
                WHEN state IN ('CA', 'TX', 'FL', 'NY', 'PA') THEN 60
                WHEN state IN ('OH', 'IL', 'MI', 'GA', 'NC') THEN 50
                WHEN state IN ('AZ', 'TN', 'MO', 'WI', 'MN') THEN 40
                ELSE 30
            END
            -- Underserved area bonus (0-40)
            + CASE WHEN is_hpsa_primary_care = TRUE THEN 40 ELSE 0 END
            -- Rural bonus (0-20)
            + CASE
                WHEN rural_status = 'Rural' THEN 20
                WHEN rural_status = 'Suburban' THEN 10
                ELSE 0
            END
        )) AS strategic_alignment_score,

        -- Financial Capacity Score (max 150)
        LEAST(150, (
            -- Operating margin points (0-100)
            CASE
                WHEN operating_margin >= 0.10 THEN 100
                WHEN operating_margin >= 0.05 THEN 80
                WHEN operating_margin >= 0.02 THEN 60
                WHEN operating_margin >= 0 THEN 40
                WHEN operating_margin IS NULL THEN 30
                ELSE 20
            END
            -- Quartile ranking points (0-50)
            + CASE
                WHEN margin_quartile = 1 THEN 50
                WHEN margin_quartile = 2 THEN 35
                WHEN margin_quartile = 3 THEN 20
                WHEN margin_quartile = 4 THEN 10
                ELSE 15
            END
        )) AS financial_capacity_score,

        -- Champion Access Score (max 150) - AI enrichment driven
        LEAST(150, (
            -- Health system presence (0-75)
            CASE
                WHEN health_system_name IS NOT NULL THEN 75
                ELSE 30
            END
            -- EMR system (0-75)
            + CASE
                WHEN emr_system ILIKE '%Epic%' THEN 75
                WHEN emr_system ILIKE '%Cerner%' THEN 65
                WHEN emr_system ILIKE '%Meditech%' THEN 50
                WHEN emr_system IS NOT NULL THEN 40
                ELSE 25
            END
        )) AS champion_access_score,

        -- Data completeness calculation
        (
            CASE WHEN tavr_volume IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN has_tavr_certification IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN cms_overall_rating IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN bed_count IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN operating_margin IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN is_hpsa_primary_care IS NOT NULL THEN 1 ELSE 0 END +
            CASE WHEN health_system_name IS NOT NULL THEN 1 ELSE 0 END
        )::DECIMAL / 7.0 AS data_completeness

    FROM hospital_data
)
SELECT
    ROW_NUMBER() OVER (ORDER BY hospital_key) AS score_id,
    hospital_key,
    CURRENT_DATE AS score_date,
    clinical_readiness_score,
    operational_readiness_score,
    strategic_alignment_score,
    financial_capacity_score,
    champion_access_score,
    0 AS bonus_points,
    0 AS penalty_points,
    (clinical_readiness_score + operational_readiness_score +
     strategic_alignment_score + financial_capacity_score +
     champion_access_score) AS total_trs,
    -- Tier classification
    CASE
        WHEN (clinical_readiness_score + operational_readiness_score +
              strategic_alignment_score + financial_capacity_score +
              champion_access_score) >= 800 THEN 'A'
        WHEN (clinical_readiness_score + operational_readiness_score +
              strategic_alignment_score + financial_capacity_score +
              champion_access_score) >= 600 THEN 'B'
        WHEN (clinical_readiness_score + operational_readiness_score +
              strategic_alignment_score + financial_capacity_score +
              champion_access_score) >= 400 THEN 'C'
        WHEN (clinical_readiness_score + operational_readiness_score +
              strategic_alignment_score + financial_capacity_score +
              champion_access_score) >= 200 THEN 'D'
        ELSE 'E'
    END AS tier_classification,
    data_completeness,
    NOW() AS _calculated_at
FROM scored;
