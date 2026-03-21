-- SQLMesh Model: Gold CMS Drug Market Profile
-- Decision-ready drug market analytics with computed market share and cost trends
-- Part of: 016-cms-puf-datasource-integration
--
-- Key design decisions:
-- 1. Spending values from silver are already prorated per NDC (no fan-out)
-- 2. Rankings use NULLS LAST to handle drugs without classification
-- 3. avg_tier_level is NULL (not 0) when no formulary data exists

MODEL (
    name hcs_gold.cms_drug_market_profile,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (ndc)),
        unique_values(columns := (ndc))
    ),
    grain (ndc)
);

WITH total_spending AS (
    SELECT
        SUM(total_part_d_spending + total_part_b_spending) AS grand_total_spending
    FROM hcs_silver.cms_drug_market
)

SELECT
    d.ndc,
    d.brand_name,
    d.generic_name,
    d.labeler_name,
    d.route,
    d.dosage_form,
    d.product_type,

    -- Spending metrics (prorated per NDC from silver layer)
    d.total_part_d_spending,
    d.total_part_d_claims,
    d.total_part_b_spending,
    d.total_part_b_claims,
    (d.total_part_d_spending + d.total_part_b_spending)                 AS total_medicare_spending,

    -- Market share by spending
    CASE
        WHEN ts.grand_total_spending > 0
        THEN ROUND(
            (d.total_part_d_spending + d.total_part_b_spending)::NUMERIC /
            ts.grand_total_spending,
            6
        )
        ELSE NULL
    END                                                                 AS market_share_by_spending,

    -- Formulary availability score (0-1 scale)
    d.formulary_coverage_pct                                            AS formulary_availability_score,
    d.avg_tier_level,  -- NULL when no formulary data (not 0)

    -- Cost trend (cost per claim as proxy)
    CASE
        WHEN (d.total_part_d_claims + d.total_part_b_claims) > 0
        THEN ROUND(
            (d.total_part_d_spending + d.total_part_b_spending)::NUMERIC /
            (d.total_part_d_claims + d.total_part_b_claims),
            2
        )
        ELSE NULL
    END                                                                 AS cost_per_claim,

    -- Classification
    d.rbcs_category,
    d.rbcs_subcategory,
    d.usp_category,
    d.usp_class,

    -- Rankings within therapeutic category (NULLS LAST for unclassified drugs)
    RANK() OVER (
        PARTITION BY d.rbcs_category
        ORDER BY (d.total_part_d_spending + d.total_part_b_spending) DESC NULLS LAST
    )                                                                   AS category_rank_by_spending,

    RANK() OVER (
        PARTITION BY d.rbcs_category
        ORDER BY d.formulary_coverage_pct DESC NULLS LAST
    )                                                                   AS category_rank_by_formulary,

    d.profile_built_at,
    NOW()                                                               AS gold_built_at

FROM hcs_silver.cms_drug_market d
CROSS JOIN total_spending ts;
