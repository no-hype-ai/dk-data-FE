-- Scoring Macros for Target Readiness Score (TRS) Calculations
-- These macros calculate domain scores and tier classifications

-- =============================================================================
-- TIER CLASSIFICATION
-- =============================================================================

-- Calculate tier classification based on total TRS score
-- A: 800+, B: 600-799, C: 400-599, D: 200-399, E: <200
@DEF calculate_tier(total_score):
    CASE
        WHEN @total_score >= 800 THEN 'A'
        WHEN @total_score >= 600 THEN 'B'
        WHEN @total_score >= 400 THEN 'C'
        WHEN @total_score >= 200 THEN 'D'
        ELSE 'E'
    END
@END;

-- =============================================================================
-- CLINICAL READINESS SCORE (Max 250 points)
-- =============================================================================

-- Calculate clinical readiness score based on TAVR volume, certification, quality
@DEF clinical_readiness_score(tavr_volume, has_certification, cms_rating, yoy_growth):
    LEAST(250, (
        -- Volume points (0-100): Higher volume = higher score
        CASE
            WHEN @tavr_volume >= 200 THEN 100
            WHEN @tavr_volume >= 100 THEN 80
            WHEN @tavr_volume >= 50 THEN 60
            WHEN @tavr_volume >= 25 THEN 40
            WHEN @tavr_volume > 0 THEN 20
            ELSE 0
        END
        -- Certification points (0-75): ACC TVC certification
        + CASE WHEN @has_certification = TRUE THEN 75 ELSE 0 END
        -- Quality rating points (0-50): CMS star rating
        + CASE
            WHEN @cms_rating = 5 THEN 50
            WHEN @cms_rating = 4 THEN 40
            WHEN @cms_rating = 3 THEN 30
            WHEN @cms_rating = 2 THEN 15
            WHEN @cms_rating = 1 THEN 5
            ELSE 0
        END
        -- Growth trajectory (0-25): Positive YoY growth
        + CASE
            WHEN @yoy_growth > 0.20 THEN 25
            WHEN @yoy_growth > 0.10 THEN 20
            WHEN @yoy_growth > 0 THEN 15
            WHEN @yoy_growth IS NULL THEN 10
            ELSE 0
        END
    ))
@END;

-- =============================================================================
-- OPERATIONAL READINESS SCORE (Max 250 points)
-- =============================================================================

-- Calculate operational readiness score based on hospital infrastructure
@DEF operational_readiness_score(bed_count, hospital_type, has_emergency, ownership_type):
    LEAST(250, (
        -- Bed capacity points (0-100)
        CASE
            WHEN @bed_count >= 500 THEN 100
            WHEN @bed_count >= 300 THEN 80
            WHEN @bed_count >= 200 THEN 60
            WHEN @bed_count >= 100 THEN 40
            WHEN @bed_count > 0 THEN 20
            ELSE 0
        END
        -- Hospital type points (0-75): Acute care hospitals preferred
        + CASE
            WHEN @hospital_type ILIKE '%Acute Care%' THEN 75
            WHEN @hospital_type ILIKE '%Critical Access%' THEN 50
            WHEN @hospital_type ILIKE '%Specialty%' THEN 40
            ELSE 25
        END
        -- Emergency services points (0-50)
        + CASE WHEN @has_emergency = TRUE THEN 50 ELSE 0 END
        -- Ownership type points (0-25): Academic/teaching preferred
        + CASE
            WHEN @ownership_type ILIKE '%Government - State%' THEN 25
            WHEN @ownership_type ILIKE '%Voluntary%' THEN 20
            WHEN @ownership_type ILIKE '%Proprietary%' THEN 15
            ELSE 10
        END
    ))
@END;

-- =============================================================================
-- STRATEGIC ALIGNMENT SCORE (Max 200 points)
-- =============================================================================

-- Calculate strategic alignment score based on market factors
@DEF strategic_alignment_score(state, network_tier, is_hpsa, rural_status):
    LEAST(200, (
        -- Network tier points (0-80)
        CASE
            WHEN @network_tier = 'Tier 1' THEN 80
            WHEN @network_tier = 'Tier 2' THEN 60
            WHEN @network_tier = 'Tier 3' THEN 40
            ELSE 20
        END
        -- Market expansion priority (0-60): Key states
        + CASE
            WHEN @state IN ('CA', 'TX', 'FL', 'NY', 'PA') THEN 60  -- Large markets
            WHEN @state IN ('OH', 'IL', 'MI', 'GA', 'NC') THEN 50  -- Growth markets
            WHEN @state IN ('AZ', 'TN', 'MO', 'WI', 'MN') THEN 40  -- Emerging markets
            ELSE 30
        END
        -- Underserved area bonus (0-40)
        + CASE WHEN @is_hpsa = TRUE THEN 40 ELSE 0 END
        -- Rural bonus (0-20): Serving rural populations
        + CASE
            WHEN @rural_status = 'Rural' THEN 20
            WHEN @rural_status = 'Suburban' THEN 10
            ELSE 0
        END
    ))
@END;

-- =============================================================================
-- FINANCIAL CAPACITY SCORE (Max 150 points)
-- =============================================================================

-- Calculate financial capacity score based on hospital financials
@DEF financial_capacity_score(operating_margin, margin_quartile):
    LEAST(150, (
        -- Operating margin points (0-100)
        CASE
            WHEN @operating_margin >= 0.10 THEN 100  -- 10%+ margin
            WHEN @operating_margin >= 0.05 THEN 80   -- 5-10% margin
            WHEN @operating_margin >= 0.02 THEN 60   -- 2-5% margin
            WHEN @operating_margin >= 0 THEN 40      -- 0-2% margin
            WHEN @operating_margin IS NULL THEN 30   -- Unknown
            ELSE 20                                   -- Negative margin
        END
        -- Quartile ranking points (0-50)
        + CASE
            WHEN @margin_quartile = 1 THEN 50  -- Top 25%
            WHEN @margin_quartile = 2 THEN 35  -- 25-50%
            WHEN @margin_quartile = 3 THEN 20  -- 50-75%
            WHEN @margin_quartile = 4 THEN 10  -- Bottom 25%
            ELSE 15                             -- Unknown
        END
    ))
@END;

-- =============================================================================
-- CHAMPION ACCESS SCORE (Max 150 points)
-- =============================================================================

-- Calculate champion access score (placeholder - enriched via AI agent)
@DEF champion_access_score(health_system_name, emr_system):
    LEAST(150, (
        -- Health system presence points (0-75)
        -- Larger health systems = more potential champions
        CASE
            WHEN @health_system_name IS NOT NULL THEN 75
            ELSE 30
        END
        -- EMR system points (0-75)
        -- Known EMR systems suggest technology readiness
        + CASE
            WHEN @emr_system ILIKE '%Epic%' THEN 75
            WHEN @emr_system ILIKE '%Cerner%' THEN 65
            WHEN @emr_system ILIKE '%Meditech%' THEN 50
            WHEN @emr_system IS NOT NULL THEN 40
            ELSE 25
        END
    ))
@END;

-- =============================================================================
-- DATA COMPLETENESS
-- =============================================================================

-- Calculate data completeness ratio (0.0 to 1.0)
@DEF data_completeness(
    has_volume, has_certification, has_rating, has_beds,
    has_financials, has_geographic, has_enrichment
):
    (
        CASE WHEN @has_volume THEN 1 ELSE 0 END +
        CASE WHEN @has_certification THEN 1 ELSE 0 END +
        CASE WHEN @has_rating THEN 1 ELSE 0 END +
        CASE WHEN @has_beds THEN 1 ELSE 0 END +
        CASE WHEN @has_financials THEN 1 ELSE 0 END +
        CASE WHEN @has_geographic THEN 1 ELSE 0 END +
        CASE WHEN @has_enrichment THEN 1 ELSE 0 END
    )::DECIMAL / 7.0
@END;
