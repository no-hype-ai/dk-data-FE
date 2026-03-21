-- SQLMesh Model: Silver CMS Geographic Analytics
-- Joins bronze geographic variation, chronic conditions, and post-acute data
-- into a unified geographic market profile
-- Part of: 016-cms-puf-datasource-integration
--
-- Key design decisions:
-- 1. Post-acute metrics are national-level only (no state/county breakdown available);
--    they are attached as context columns, not county-attributed metrics
-- 2. Chronic conditions are state-level only (CMS publishes at state grain);
--    county-level rows inherit their state's chronic condition data
-- 3. Latest year filter applied to all source CTEs

MODEL (
    name hcs_silver.cms_geographic,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (state, county)),
        unique_values(columns := (state, county))
    ),
    grain (state, county)
);

WITH latest_geo AS (
    SELECT
        state,
        county,
        bene_count                              AS total_beneficiaries,
        total_actual_costs,
        per_capita_costs,
        year
    FROM bronze.cms_geographic_variation
    WHERE year = (SELECT MAX(year) FROM bronze.cms_geographic_variation)
),

-- Chronic conditions: state-level only (CMS does not publish county-level)
chronic_pivot AS (
    SELECT
        state,
        ARRAY_AGG(DISTINCT condition ORDER BY condition) AS top_chronic_conditions,
        AVG(prevalence_rate)                    AS avg_chronic_prevalence
    FROM bronze.cms_chronic_conditions
    GROUP BY state
),

-- Post-acute: national-level aggregates only
-- These are NOT county-specific; they provide system-wide context
post_acute_national AS (
    SELECT
        SUM(total_episodes)                     AS national_post_acute_episodes,
        SUM(CASE WHEN UPPER(TRIM(provider_type)) = 'SNF' THEN total_episodes ELSE 0 END) AS national_snf_episodes,
        SUM(CASE WHEN UPPER(TRIM(provider_type)) = 'HHA' THEN total_episodes ELSE 0 END) AS national_hha_episodes,
        AVG(avg_spending_per_episode)           AS national_avg_spending_per_episode
    FROM bronze.cms_post_acute
    WHERE year = (SELECT MAX(year) FROM bronze.cms_post_acute)
),

national_bene_total AS (
    SELECT SUM(total_beneficiaries) AS total FROM latest_geo
)

SELECT
    g.state,
    g.county,
    g.total_beneficiaries,
    g.total_actual_costs,
    g.per_capita_costs,
    g.year                                                              AS data_year,

    -- Chronic conditions (state-level; inherited by all counties in state)
    COALESCE(c.top_chronic_conditions, ARRAY[]::TEXT[])                  AS top_chronic_conditions,
    COALESCE(c.avg_chronic_prevalence, 0)                               AS avg_chronic_prevalence,

    -- National post-acute context (same value for all rows — not county-specific)
    CASE
        WHEN nbt.total > 0
        THEN ROUND(
            pan.national_post_acute_episodes::NUMERIC / nbt.total,
            4
        )
        ELSE NULL
    END                                                                 AS national_post_acute_utilization_rate,
    pan.national_avg_spending_per_episode,

    NOW()                                                               AS profile_built_at

FROM latest_geo g
LEFT JOIN chronic_pivot c ON g.state = c.state
CROSS JOIN post_acute_national pan
CROSS JOIN national_bene_total nbt;
