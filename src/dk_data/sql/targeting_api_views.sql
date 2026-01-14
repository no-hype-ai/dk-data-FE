-- TAVR Targeting API Views
-- Feature: 002-tavr-targeting-tool
-- Tasks: T047-T050
--
-- These views are exposed via PostgREST for API access.
-- Run after targeting_tables.sql and after SQLMesh models are deployed.

-- ============================================================================
-- T047: api.targeting view (alias for targeting_acceleration)
-- Main targeting endpoint with all scores and data
-- ============================================================================

CREATE OR REPLACE VIEW api.targeting AS
SELECT
    -- Hospital identifiers
    h.hospital_id,
    h.hospital_name,
    h.health_system_name,
    h.state,
    h.city,

    -- Segment classification
    CASE
        WHEN COALESCE(br.is_current_client, FALSE) THEN 'Optimization'
        ELSE 'Acceleration'
    END AS segment,

    -- Priority classification (computed)
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

    -- Targeting score (0-6)
    (
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
    ) AS targeting_score,

    -- Component scores
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
    CASE WHEN vh.yoy_growth_pct > 20 THEN 2 WHEN vh.yoy_growth_pct > 0 THEN 1 ELSE 0 END AS growth_score,
    CASE WHEN COALESCE(vh.total_tavr_volume, 0) >= 100 THEN 1 ELSE 0 END AS volume_score,
    CASE WHEN e.primary_emr IN ('Epic', 'Cerner') THEN 1 ELSE 0 END AS emr_score,

    -- Volume data
    vh.total_tavr_volume,
    vh.yoy_growth_pct,
    vh.market_share_pct,

    -- Biome relationship
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

    -- EMR
    e.primary_emr,

    -- Hospital details
    h.bed_count,
    CASE
        WHEN h.bed_count >= 500 THEN 'Large'
        WHEN h.bed_count >= 200 THEN 'Medium'
        ELSE 'Small'
    END AS bed_size_category,

    -- Champions
    cc.champion_name AS clinical_champion,
    cc.engagement_level AS clinical_engagement,
    ac.champion_name AS admin_champion,
    ac.engagement_level AS admin_engagement

FROM mart.dim_hospital h
LEFT JOIN targeting.biome_relationships br ON h.hospital_id = br.hospital_id
LEFT JOIN targeting.sales_coverage sc ON h.hospital_id = sc.hospital_id
LEFT JOIN targeting.volume_history vh ON h.hospital_id = vh.hospital_id
    AND vh.fiscal_year = (SELECT MAX(fiscal_year) FROM targeting.volume_history)
LEFT JOIN targeting.emr_systems e ON h.hospital_id = e.hospital_id
LEFT JOIN LATERAL (
    SELECT champion_name, engagement_level
    FROM targeting.champions
    WHERE hospital_id = h.hospital_id AND champion_type = 'Clinical'
    ORDER BY CASE engagement_level WHEN 'Advocating' THEN 1 WHEN 'Interested' THEN 2 WHEN 'Passive' THEN 3 ELSE 4 END
    LIMIT 1
) cc ON TRUE
LEFT JOIN LATERAL (
    SELECT champion_name, engagement_level
    FROM targeting.champions
    WHERE hospital_id = h.hospital_id AND champion_type = 'Administrative'
    ORDER BY CASE engagement_level WHEN 'Advocating' THEN 1 WHEN 'Interested' THEN 2 WHEN 'Passive' THEN 3 ELSE 4 END
    LIMIT 1
) ac ON TRUE
WHERE COALESCE(vh.total_tavr_volume, 0) > 0;

COMMENT ON VIEW api.targeting IS 'Main targeting endpoint with scores, segments, and hospital data';

-- ============================================================================
-- api.targeting_summary view
-- Aggregated counts by segment and priority
-- ============================================================================

CREATE OR REPLACE VIEW api.targeting_summary AS
SELECT
    segment,
    priority,
    COUNT(*) AS hospital_count,
    SUM(total_tavr_volume) AS total_volume,
    AVG(total_tavr_volume)::INTEGER AS avg_volume,
    ROUND(AVG(yoy_growth_pct)::NUMERIC, 2) AS avg_growth,
    SUM(CASE WHEN expressed_interest THEN 1 ELSE 0 END) AS interested_count,
    SUM(COALESCE(phase_2_tokens_needed, 0)) AS total_tokens_needed
FROM api.targeting
GROUP BY segment, priority
ORDER BY
    segment,
    CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END;

COMMENT ON VIEW api.targeting_summary IS 'Aggregated targeting summary by segment and priority';

-- ============================================================================
-- T048: api.coverage view
-- Sales coverage data
-- ============================================================================

CREATE OR REPLACE VIEW api.coverage AS
SELECT
    sc.hospital_id,
    h.hospital_name,
    sc.region,
    sc.territory,
    sc.regional_director,
    sc.rd_email,
    sc.area_vp,
    sc.avp_email,
    sc.expressed_interest,
    sc.last_contact_date,
    sc.next_scheduled_contact,
    sc.engagement_notes
FROM targeting.sales_coverage sc
JOIN mart.dim_hospital h ON sc.hospital_id = h.hospital_id;

COMMENT ON VIEW api.coverage IS 'Sales territory assignments and engagement tracking';

-- ============================================================================
-- T049: api.champions view
-- Champion contact and engagement data
-- ============================================================================

CREATE OR REPLACE VIEW api.champions AS
SELECT
    c.id,
    c.hospital_id,
    h.hospital_name,
    c.champion_type,
    c.champion_name,
    c.title,
    c.specialty,
    c.engagement_level,
    c.last_engagement_date,
    c.kol_status
    -- Note: email, phone, linkedin_url excluded for privacy (use champions_full for authorized access)
FROM targeting.champions c
JOIN mart.dim_hospital h ON c.hospital_id = h.hospital_id;

COMMENT ON VIEW api.champions IS 'Champion contact and engagement information (limited fields for privacy)';

-- ============================================================================
-- T050: Grant SELECT permissions on all API views
-- ============================================================================

GRANT SELECT ON api.targeting TO api_user;
GRANT SELECT ON api.targeting_summary TO api_user;
GRANT SELECT ON api.coverage TO api_user;
GRANT SELECT ON api.champions TO api_user;

-- Verify views were created
DO $$
DECLARE
    view_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO view_count
    FROM information_schema.views
    WHERE table_schema = 'api'
      AND table_name IN ('targeting', 'targeting_summary', 'coverage', 'champions');

    IF view_count = 4 THEN
        RAISE NOTICE 'SUCCESS: All 4 API views created';
    ELSE
        RAISE WARNING 'WARNING: Expected 4 views, found %', view_count;
    END IF;
END $$;
