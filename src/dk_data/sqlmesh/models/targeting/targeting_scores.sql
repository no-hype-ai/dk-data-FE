-- TAVR Targeting Scores Model
-- Feature: 002-tavr-targeting-tool
-- Tasks: T036-T042, T019, T025

MODEL (
    name hcs_gold.targeting_scores,
    kind VIEW,
    cron '@daily',
    description 'Main targeting view combining all factors with computed scores'
);

-- ============================================================================
-- api.targeting_acceleration view
-- T036: Create targeting view
-- T037: biome_score (0-2)
-- T038: growth_score (0-2)
-- T039: volume_score (0-1)
-- T040: emr_score (0-1)
-- T041: targeting_score (0-6)
-- T042: priority classification
-- ============================================================================

-- Legacy TAVR CRM tables no longer exist; return empty relations with correct schemas
-- so all downstream COALESCE calls yield their default values.
WITH biome_rel AS (
    SELECT
        NULL::TEXT      AS hospital_id,
        FALSE           AS is_current_client,
        FALSE           AS echo_surveillance_active,
        FALSE           AS workflow_active,
        FALSE           AS analytics_active,
        NULL::TEXT      AS pilot_phase,
        NULL::TEXT      AS contract_type,
        NULL::INTEGER   AS phase_2_tokens_needed
    WHERE FALSE
),
sales_cov AS (
    SELECT
        NULL::TEXT      AS hospital_id,
        NULL::TEXT      AS regional_director,
        NULL::TEXT      AS area_vp,
        FALSE           AS expressed_interest
    WHERE FALSE
),
vol_hist AS (
    SELECT
        NULL::TEXT      AS hospital_id,
        NULL::INTEGER   AS fiscal_year,
        NULL::INTEGER   AS total_tavr_volume,
        NULL::NUMERIC   AS yoy_growth_pct,
        NULL::NUMERIC   AS market_share_pct
    WHERE FALSE
),
emr_sys AS (
    SELECT
        NULL::TEXT      AS hospital_id,
        NULL::TEXT      AS primary_emr
    WHERE FALSE
),
champs AS (
    SELECT
        NULL::TEXT      AS hospital_id,
        NULL::TEXT      AS champion_name,
        NULL::TEXT      AS champion_type,
        NULL::TEXT      AS engagement_level
    WHERE FALSE
)

SELECT
    -- Hospital identifiers
    h.hospital_id,
    h.hospital_name,
    h.health_system_name,
    h.state,
    h.city,

    -- Raw relationship data
    COALESCE(br.is_current_client, FALSE) AS is_current_client,
    COALESCE(br.echo_surveillance_active, FALSE) AS echo_surveillance_active,
    COALESCE(br.workflow_active, FALSE) AS workflow_active,
    COALESCE(br.analytics_active, FALSE) AS analytics_active,
    br.pilot_phase,
    br.contract_type,
    br.phase_2_tokens_needed,

    -- Sales coverage
    sc.regional_director,
    sc.area_vp,
    COALESCE(sc.expressed_interest, FALSE) AS expressed_interest,

    -- Volume data (latest year)
    vh.total_tavr_volume,
    vh.yoy_growth_pct,
    vh.market_share_pct,

    -- EMR data
    e.primary_emr,

    -- ========================================================================
    -- T037: Biome Score (0-2)
    -- T019: biome_score calculation
    -- 0 = No relationship (not a client)
    -- 1 = Partial platform (any single component active)
    -- 2 = Full platform (all three components active)
    -- ========================================================================
    CASE
        WHEN COALESCE(br.echo_surveillance_active, FALSE)
             AND COALESCE(br.workflow_active, FALSE)
             AND COALESCE(br.analytics_active, FALSE)
        THEN 2
        WHEN COALESCE(br.echo_surveillance_active, FALSE)
             OR COALESCE(br.workflow_active, FALSE)
             OR COALESCE(br.analytics_active, FALSE)
        THEN 1
        ELSE 0
    END AS biome_score,

    -- ========================================================================
    -- T038: Growth Score (0-2)
    -- T025: growth_score calculation
    -- 0 = Declining or flat (YoY <= 0%)
    -- 1 = Moderate growth (0% < YoY <= 20%)
    -- 2 = High growth (YoY > 20%)
    -- ========================================================================
    CASE
        WHEN vh.yoy_growth_pct > 20 THEN 2
        WHEN vh.yoy_growth_pct > 0 THEN 1
        ELSE 0
    END AS growth_score,

    -- ========================================================================
    -- T039: Volume Score (0-1)
    -- 0 = Below minimum threshold (< 100 procedures/year)
    -- 1 = Meets minimum threshold (>= 100 procedures/year)
    -- ========================================================================
    CASE
        WHEN COALESCE(vh.total_tavr_volume, 0) >= 100 THEN 1
        ELSE 0
    END AS volume_score,

    -- ========================================================================
    -- T040: EMR Score (0-1)
    -- 0 = Other EMR or unknown
    -- 1 = Epic or Cerner (preferred integration partners)
    -- ========================================================================
    CASE
        WHEN e.primary_emr IN ('Epic', 'Cerner') THEN 1
        ELSE 0
    END AS emr_score,

    -- ========================================================================
    -- T041: Composite Targeting Score (0-6)
    -- Sum of all component scores
    -- ========================================================================
    (
        -- biome_score (0-2)
        CASE
            WHEN COALESCE(br.echo_surveillance_active, FALSE)
                 AND COALESCE(br.workflow_active, FALSE)
                 AND COALESCE(br.analytics_active, FALSE)
            THEN 2
            WHEN COALESCE(br.echo_surveillance_active, FALSE)
                 OR COALESCE(br.workflow_active, FALSE)
                 OR COALESCE(br.analytics_active, FALSE)
            THEN 1
            ELSE 0
        END
        +
        -- growth_score (0-2)
        CASE
            WHEN vh.yoy_growth_pct > 20 THEN 2
            WHEN vh.yoy_growth_pct > 0 THEN 1
            ELSE 0
        END
        +
        -- volume_score (0-1)
        CASE WHEN COALESCE(vh.total_tavr_volume, 0) >= 100 THEN 1 ELSE 0 END
        +
        -- emr_score (0-1)
        CASE WHEN e.primary_emr IN ('Epic', 'Cerner') THEN 1 ELSE 0 END
    ) AS targeting_score,

    -- ========================================================================
    -- T042: Priority Classification
    -- Based on targeting_score:
    -- High: 5-6 points
    -- Medium: 3-4 points
    -- Low: 1-2 points
    -- DNQ: 0 points
    -- ========================================================================
    CASE
        WHEN (
            CASE
                WHEN COALESCE(br.echo_surveillance_active, FALSE)
                     AND COALESCE(br.workflow_active, FALSE)
                     AND COALESCE(br.analytics_active, FALSE)
                THEN 2
                WHEN COALESCE(br.echo_surveillance_active, FALSE)
                     OR COALESCE(br.workflow_active, FALSE)
                     OR COALESCE(br.analytics_active, FALSE)
                THEN 1
                ELSE 0
            END
            + CASE WHEN vh.yoy_growth_pct > 20 THEN 2 WHEN vh.yoy_growth_pct > 0 THEN 1 ELSE 0 END
            + CASE WHEN COALESCE(vh.total_tavr_volume, 0) >= 100 THEN 1 ELSE 0 END
            + CASE WHEN e.primary_emr IN ('Epic', 'Cerner') THEN 1 ELSE 0 END
        ) >= 5 THEN 'High'
        WHEN (
            CASE
                WHEN COALESCE(br.echo_surveillance_active, FALSE)
                     AND COALESCE(br.workflow_active, FALSE)
                     AND COALESCE(br.analytics_active, FALSE)
                THEN 2
                WHEN COALESCE(br.echo_surveillance_active, FALSE)
                     OR COALESCE(br.workflow_active, FALSE)
                     OR COALESCE(br.analytics_active, FALSE)
                THEN 1
                ELSE 0
            END
            + CASE WHEN vh.yoy_growth_pct > 20 THEN 2 WHEN vh.yoy_growth_pct > 0 THEN 1 ELSE 0 END
            + CASE WHEN COALESCE(vh.total_tavr_volume, 0) >= 100 THEN 1 ELSE 0 END
            + CASE WHEN e.primary_emr IN ('Epic', 'Cerner') THEN 1 ELSE 0 END
        ) >= 3 THEN 'Medium'
        WHEN (
            CASE
                WHEN COALESCE(br.echo_surveillance_active, FALSE)
                     AND COALESCE(br.workflow_active, FALSE)
                     AND COALESCE(br.analytics_active, FALSE)
                THEN 2
                WHEN COALESCE(br.echo_surveillance_active, FALSE)
                     OR COALESCE(br.workflow_active, FALSE)
                     OR COALESCE(br.analytics_active, FALSE)
                THEN 1
                ELSE 0
            END
            + CASE WHEN vh.yoy_growth_pct > 20 THEN 2 WHEN vh.yoy_growth_pct > 0 THEN 1 ELSE 0 END
            + CASE WHEN COALESCE(vh.total_tavr_volume, 0) >= 100 THEN 1 ELSE 0 END
            + CASE WHEN e.primary_emr IN ('Epic', 'Cerner') THEN 1 ELSE 0 END
        ) >= 1 THEN 'Low'
        ELSE 'DNQ'
    END AS priority,

    -- Hospital details for context
    h.bed_count,
    CASE
        WHEN h.bed_count >= 500 THEN 'Large'
        WHEN h.bed_count >= 200 THEN 'Medium'
        ELSE 'Small'
    END AS bed_size_category,
    h.hospital_type,
    h.ownership_type,

    -- Champion info (first of each type)
    cc.champion_name AS clinical_champion,
    cc.engagement_level AS clinical_engagement,
    ac.champion_name AS admin_champion,
    ac.engagement_level AS admin_engagement

FROM hcs_gold.dim_hospital h
LEFT JOIN biome_rel br ON h.hospital_id = br.hospital_id
LEFT JOIN sales_cov sc ON h.hospital_id = sc.hospital_id
LEFT JOIN vol_hist vh ON h.hospital_id = vh.hospital_id
    AND vh.fiscal_year = (SELECT MAX(fiscal_year) FROM vol_hist)
LEFT JOIN emr_sys e ON h.hospital_id = e.hospital_id
LEFT JOIN LATERAL (
    SELECT champion_name, engagement_level
    FROM champs
    WHERE hospital_id = h.hospital_id AND champion_type = 'Clinical'
    ORDER BY
        CASE engagement_level
            WHEN 'Advocating' THEN 1
            WHEN 'Interested' THEN 2
            WHEN 'Passive' THEN 3
            ELSE 4
        END
    LIMIT 1
) cc ON TRUE
LEFT JOIN LATERAL (
    SELECT champion_name, engagement_level
    FROM champs
    WHERE hospital_id = h.hospital_id AND champion_type = 'Administrative'
    ORDER BY
        CASE engagement_level
            WHEN 'Advocating' THEN 1
            WHEN 'Interested' THEN 2
            WHEN 'Passive' THEN 3
            ELSE 4
        END
    LIMIT 1
) ac ON TRUE
WHERE COALESCE(vh.total_tavr_volume, 0) > 0;
