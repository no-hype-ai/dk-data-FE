-- SQLMesh Model: Gold CMS Drug Market Profile
-- Extends hcs_silver.cms_drug_market with market share and spending rank analytics,
-- enriched with Medicaid cross-program utilization from hcs_silver.drug_utilization.
-- Feature: 019-cms-puf-platform-reconciliation (T014)
--
-- Grain: (generic_name, _source_year)
-- Silver sources:
--   1. hcs_silver.cms_drug_market   — Medicare Part D + Part B combined view
--   2. hcs_silver.drug_utilization  — Medicaid spending; molecule linkage confirmation

MODEL (
    name hcs_gold.cms_drug_market_profile,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (generic_name, _source_year))
    ),
    grain (generic_name, _source_year),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
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

-- Medicaid utilization from the 019 drug_utilization silver (6-source model)
-- Join on normalized generic name to pull cross-program Medicaid figures
medicaid_util AS (
    SELECT
        drug_or_hcpcs_code,
        _source_year,
        SUM(medicaid_amount)                AS medicaid_spending,
        SUM(medicaid_prescriptions)         AS medicaid_prescriptions,
        SUM(total_beneficiaries)            AS medicaid_beneficiaries,
        molecule_id                         AS du_molecule_id
    FROM hcs_silver.drug_utilization
    WHERE code_type = 'medicaid_drug'
      AND drug_or_hcpcs_code IS NOT NULL
    GROUP BY drug_or_hcpcs_code, _source_year, molecule_id
),

-- Total spending per year for market share denominator (Medicare only for comparability)
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
        -- Medicaid cross-program data (joined on normalized generic name)
        m.medicaid_spending,
        m.medicaid_prescriptions,
        m.medicaid_beneficiaries,
        -- Prefer cms_drug_market molecule_id; fall back to drug_utilization lookup
        COALESCE(b.molecule_id, m.du_molecule_id) AS resolved_molecule_id,

        -- Market share: this drug's Medicare spending / all drugs Medicare spending
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
    LEFT JOIN medicaid_util m
        ON LOWER(REGEXP_REPLACE(b.generic_name, '[^a-zA-Z0-9]', '', 'g'))
           = m.drug_or_hcpcs_code
       AND b._source_year = m._source_year
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
    -- Medicare combined
    total_spending,
    total_beneficiaries,
    avg_spending_per_beneficiary,
    -- Medicaid cross-program (from drug_utilization silver)
    medicaid_spending,
    medicaid_prescriptions,
    medicaid_beneficiaries,
    -- Total cross-program spending (Medicare + Medicaid)
    COALESCE(total_spending, 0) + COALESCE(medicaid_spending, 0)        AS total_cross_program_spending,
    -- Market analytics (Medicare)
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
    resolved_molecule_id                    AS molecule_id,
    created_at,
    updated_at
FROM ranked;
