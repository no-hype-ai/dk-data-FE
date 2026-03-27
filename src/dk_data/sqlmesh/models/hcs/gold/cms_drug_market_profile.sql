-- SQLMesh Model: Gold CMS Drug Market Profile
-- Extends hcs_silver.cms_drug_market with market share and spending rank analytics.
-- Feature: 019-cms-puf-platform-reconciliation (T014)
--
-- Grain: (generic_name, _source_year)
-- Source: hcs_silver.cms_drug_market

MODEL (
    name hcs_gold.cms_drug_market_profile,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (generic_name, _source_year))
    ),
    grain (generic_name, _source_year)
);

WITH base AS (
    SELECT
        id,
        generic_name,
        brand_name,
        manufacturer_name,
        hcpcs_code,
        _source_year,
        part_d_spending,
        part_d_claims,
        part_d_beneficiaries,
        part_d_dosage_units,
        part_d_avg_cost_per_claim,
        part_d_avg_cost_per_bene,
        part_b_spending,
        part_b_claims,
        part_b_beneficiaries,
        part_b_dosage_units,
        part_b_avg_cost_per_claim,
        part_b_avg_cost_per_bene,
        total_spending,
        total_beneficiaries,
        avg_spending_per_beneficiary,
        molecule_id,
        created_at,
        updated_at
    FROM hcs_silver.cms_drug_market
),

-- Total spending per year for market share denominator
year_totals AS (
    SELECT
        _source_year,
        SUM(total_spending) AS year_total_spending
    FROM base
    GROUP BY _source_year
),

-- Compute market share and spending rank
ranked AS (
    SELECT
        b.*,
        -- Market share: this drug's spending / all drugs spending in same year
        CASE
            WHEN yt.year_total_spending > 0
            THEN b.total_spending / yt.year_total_spending
            ELSE NULL
        END AS market_share_pct,

        -- Spending rank within year (1 = highest spending)
        RANK() OVER (
            PARTITION BY b._source_year
            ORDER BY b.total_spending DESC NULLS LAST
        ) AS spending_rank_in_year,

        -- Part D spending rank within year
        RANK() OVER (
            PARTITION BY b._source_year
            ORDER BY b.part_d_spending DESC NULLS LAST
        ) AS part_d_spending_rank,

        -- Part B spending rank within year
        RANK() OVER (
            PARTITION BY b._source_year
            ORDER BY b.part_b_spending DESC NULLS LAST
        ) AS part_b_spending_rank,

        -- Claims percentile (for demand signal)
        PERCENT_RANK() OVER (
            PARTITION BY b._source_year
            ORDER BY b.part_d_claims ASC NULLS LAST
        ) AS part_d_claims_percentile

    FROM base b
    JOIN year_totals yt ON b._source_year = yt._source_year
)

SELECT
    id,
    generic_name,
    brand_name,
    manufacturer_name,
    hcpcs_code,
    _source_year,
    -- Part D spending components
    part_d_spending,
    part_d_claims,
    part_d_beneficiaries,
    part_d_dosage_units,
    part_d_avg_cost_per_claim,
    part_d_avg_cost_per_bene,
    -- Part B spending components
    part_b_spending,
    part_b_claims,
    part_b_beneficiaries,
    part_b_dosage_units,
    part_b_avg_cost_per_claim,
    part_b_avg_cost_per_bene,
    -- Combined
    total_spending,
    total_beneficiaries,
    avg_spending_per_beneficiary,
    -- Market analytics
    market_share_pct,
    spending_rank_in_year,
    part_d_spending_rank,
    part_b_spending_rank,
    part_d_claims_percentile,
    -- Tier classification based on spending rank
    CASE
        WHEN spending_rank_in_year <= 50   THEN 'tier_1_top50'
        WHEN spending_rank_in_year <= 250  THEN 'tier_2_top250'
        WHEN spending_rank_in_year <= 1000 THEN 'tier_3_top1000'
        ELSE 'tier_4_long_tail'
    END                                     AS market_tier,
    molecule_id,
    created_at,
    updated_at
FROM ranked;
