-- SQLMesh Model: Silver CMS Drug Market
-- Joins bronze NDC, Part D/B spending, formulary, and classification data
-- into a unified drug market profile
-- Part of: 016-cms-puf-datasource-integration
--
-- Key design decisions:
-- 1. Spending is filtered to latest year only (avoids multi-year aggregation)
-- 2. Part B spending joins via hcpcs_description ≈ nonproprietary_name (no generic_name in Part B)
-- 3. Spending is prorated across NDCs sharing the same drug name to prevent fan-out
-- 4. USP deduplicated to first category per NDC to preserve grain uniqueness
-- 5. RBCS joins directly via Part B hcpcs_code (RBCS is HCPCS-keyed)

MODEL (
    name silver.cms_drug_market,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (ndc)),
        unique_values(columns := (ndc))
    ),
    grain (ndc)
);

-- Count NDCs per drug name to prorate drug-level spending across NDCs
WITH ndc_per_drug AS (
    SELECT
        nonproprietary_name,
        COUNT(*)                                    AS ndc_count
    FROM bronze.cms_ndc
    WHERE nonproprietary_name IS NOT NULL
    GROUP BY nonproprietary_name
),

-- Part D spending: latest year only, grouped by generic_name
spending_d AS (
    SELECT
        generic_name,
        SUM(total_spending)                         AS total_part_d_spending,
        SUM(total_claims)                           AS total_part_d_claims
    FROM bronze.cms_part_d_spending
    WHERE year = (SELECT MAX(year) FROM bronze.cms_part_d_spending)
    GROUP BY generic_name
),

-- Part B spending: latest year only, grouped by hcpcs_code
-- Note: Part B has no generic_name column; hcpcs_description serves as drug identifier
spending_b AS (
    SELECT
        hcpcs_code,
        hcpcs_description,
        SUM(total_spending)                         AS total_part_b_spending,
        SUM(total_claims)                           AS total_part_b_claims
    FROM bronze.cms_part_b_spending
    WHERE hcpcs_code IS NOT NULL
      AND year = (SELECT MAX(year) FROM bronze.cms_part_b_spending)
    GROUP BY hcpcs_code, hcpcs_description
),

formulary_coverage AS (
    SELECT
        ndc,
        COUNT(DISTINCT formulary_id)                AS formulary_count,
        ROUND(
            COUNT(DISTINCT formulary_id)::NUMERIC /
            NULLIF((SELECT COUNT(DISTINCT formulary_id) FROM bronze.cms_formulary), 0),
            4
        )                                           AS formulary_coverage_pct,
        ROUND(AVG(tier_level)::NUMERIC, 1)          AS avg_tier_level
    FROM bronze.cms_formulary
    GROUP BY ndc
),

-- Deduplicate USP: one category per NDC (alphabetically first)
usp_lookup AS (
    SELECT DISTINCT ON (ndc)
        ndc,
        usp_category,
        usp_class
    FROM bronze.cms_usp
    WHERE ndc IS NOT NULL
    ORDER BY ndc, usp_category, usp_class
)

SELECT
    n.ndc,
    n.proprietary_name                                                      AS brand_name,
    n.nonproprietary_name                                                   AS generic_name,
    n.labeler_name,
    n.route,
    n.dosage_form,
    n.product_type,

    -- Part D spending (prorated across NDCs sharing the same generic_name)
    COALESCE(
        ROUND(sd.total_part_d_spending / NULLIF(ndc_ct.ndc_count, 0), 2),
        0
    )                                                                       AS total_part_d_spending,
    COALESCE(
        ROUND(sd.total_part_d_claims::NUMERIC / NULLIF(ndc_ct.ndc_count, 0), 0)::INTEGER,
        0
    )                                                                       AS total_part_d_claims,

    -- Part B spending (joined via hcpcs_description ≈ nonproprietary_name)
    COALESCE(sb.total_part_b_spending, 0)                                   AS total_part_b_spending,
    COALESCE(sb.total_part_b_claims, 0)                                     AS total_part_b_claims,

    -- Formulary coverage
    COALESCE(f.formulary_coverage_pct, 0)                                   AS formulary_coverage_pct,
    f.avg_tier_level,  -- NULL when no formulary data (not 0)

    -- Classifications
    -- RBCS joins via Part B hcpcs_code (RBCS is HCPCS-keyed, not NDC-keyed)
    r.rbcs_category,
    r.rbcs_subcategory,
    u.usp_category,
    u.usp_class,

    NOW()                                                                   AS profile_built_at

FROM bronze.cms_ndc n
LEFT JOIN ndc_per_drug ndc_ct ON n.nonproprietary_name = ndc_ct.nonproprietary_name
LEFT JOIN spending_d sd ON n.nonproprietary_name = sd.generic_name
LEFT JOIN spending_b sb ON n.nonproprietary_name = sb.hcpcs_description
LEFT JOIN formulary_coverage f ON n.ndc = f.ndc
LEFT JOIN bronze.cms_rbcs r ON sb.hcpcs_code = r.hcpcs_code
LEFT JOIN usp_lookup u ON n.ndc = u.ndc;
