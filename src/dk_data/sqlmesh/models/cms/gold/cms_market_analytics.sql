-- SQLMesh Model: Gold CMS Market Analytics
-- Decision-ready geographic market analytics with normalized indices and burden scores
-- Part of: 016-cms-puf-datasource-integration

MODEL (
    name gold.cms_market_analytics,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (state, county)),
        unique_values(columns := (state, county))
    ),
    grain (state, county)
);

WITH national_avg AS (
    SELECT
        AVG(per_capita_costs)                   AS avg_per_capita_costs,
        AVG(avg_chronic_prevalence)             AS avg_chronic_prevalence,
        AVG(post_acute_utilization_rate)        AS avg_post_acute_rate
    FROM silver.cms_geographic
)

SELECT
    g.state,
    g.county,
    g.total_beneficiaries,
    g.total_actual_costs,
    g.per_capita_costs,
    g.data_year,

    -- Cost index: normalized per-capita costs relative to national average
    CASE
        WHEN n.avg_per_capita_costs > 0
        THEN ROUND(g.per_capita_costs / n.avg_per_capita_costs, 4)
        ELSE NULL
    END                                                                 AS cost_index,

    -- Chronic conditions
    g.top_chronic_conditions,
    g.avg_chronic_prevalence,

    -- Chronic burden score: normalized chronic prevalence relative to national average
    CASE
        WHEN n.avg_chronic_prevalence > 0
        THEN ROUND(g.avg_chronic_prevalence / n.avg_chronic_prevalence, 4)
        ELSE NULL
    END                                                                 AS chronic_burden_score,

    -- Post-acute utilization
    g.post_acute_utilization_rate,

    -- Post-acute dependency ratio: normalized utilization relative to national average
    CASE
        WHEN n.avg_post_acute_rate > 0
        THEN ROUND(g.post_acute_utilization_rate / n.avg_post_acute_rate, 4)
        ELSE NULL
    END                                                                 AS post_acute_dependency_ratio,

    -- State-level rankings
    RANK() OVER (
        PARTITION BY g.state
        ORDER BY g.per_capita_costs DESC
    )                                                                   AS state_rank_cost,

    RANK() OVER (
        PARTITION BY g.state
        ORDER BY g.total_beneficiaries DESC
    )                                                                   AS state_rank_beneficiaries,

    g.profile_built_at,
    NOW()                                                               AS gold_built_at

FROM silver.cms_geographic g
CROSS JOIN national_avg n;
