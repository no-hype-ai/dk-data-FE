-- SQLMesh Model: Silver CMS Drug Market
-- Aggregates Medicare Part D and Part B drug spending into unified drug market view.
-- Feature: 019-cms-puf-platform-reconciliation (T013)
--
-- Grain: (generic_name, _source_year)
-- Sources: hcs_bronze.cms_part_d_spending, hcs_bronze.cms_part_b_spending
--
-- Column names match CMS API (snake_case):
--   Part D: gnrc_name, brnd_name, tot_spndng, tot_clms, tot_benes,
--           avg_spnd_per_clm, avg_spnd_per_bene
--   Part B: hcpcs_cd, hcpcs_desc, mftr_name, tot_spndng, tot_clms,
--           tot_benes, avg_spnd_per_clm, avg_spnd_per_bene

MODEL (
    name hcs_silver.cms_drug_market,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (generic_name, _source_year))
    ),
    grain (generic_name, _source_year)
);

WITH part_d AS (
    -- Group by generic only (not brand) to match grain (generic_name, _source_year).
    -- A generic can have multiple brand names; spending is aggregated across all brands.
    SELECT
        gnrc_name                                           AS generic_name,
        STRING_AGG(DISTINCT brnd_name, ', '
            ORDER BY brnd_name)                             AS brand_name,
        NULL::TEXT                                          AS manufacturer_name,
        _source_year,
        SUM(tot_spndng)                                     AS part_d_spending,
        SUM(tot_clms)                                       AS part_d_claims,
        SUM(tot_benes)                                      AS part_d_beneficiaries,
        SUM(tot_dsg_unts)                                   AS part_d_dosage_units,
        AVG(avg_spnd_per_clm)                               AS part_d_avg_cost_per_claim,
        AVG(avg_spnd_per_bene)                              AS part_d_avg_cost_per_bene
    FROM hcs_bronze.cms_part_d_spending
    WHERE gnrc_name IS NOT NULL
    GROUP BY gnrc_name, _source_year
),

part_b AS (
    SELECT
        hcpcs_desc                              AS generic_name,
        hcpcs_cd                                AS hcpcs_code,
        mftr_name                               AS manufacturer_name,
        _source_year,
        SUM(tot_spndng)                         AS part_b_spending,
        SUM(tot_clms)                           AS part_b_claims,
        SUM(tot_benes)                          AS part_b_beneficiaries,
        SUM(tot_dsg_unts)                       AS part_b_dosage_units,
        AVG(avg_spnd_per_clm)                   AS part_b_avg_cost_per_claim,
        AVG(avg_spnd_per_bene)                  AS part_b_avg_cost_per_bene
    FROM hcs_bronze.cms_part_b_spending
    WHERE hcpcs_desc IS NOT NULL
    GROUP BY hcpcs_desc, hcpcs_cd, mftr_name, _source_year
),

combined AS (
    SELECT
        COALESCE(d.generic_name, b.generic_name)    AS generic_name,
        d.brand_name,
        COALESCE(d.manufacturer_name, b.manufacturer_name) AS manufacturer_name,
        b.hcpcs_code,
        COALESCE(d._source_year, b._source_year)    AS _source_year,
        COALESCE(d.part_d_spending, 0)              AS part_d_spending,
        COALESCE(d.part_d_claims, 0)                AS part_d_claims,
        COALESCE(d.part_d_beneficiaries, 0)         AS part_d_beneficiaries,
        COALESCE(d.part_d_dosage_units, 0)          AS part_d_dosage_units,
        d.part_d_avg_cost_per_claim,
        d.part_d_avg_cost_per_bene,
        COALESCE(b.part_b_spending, 0)              AS part_b_spending,
        COALESCE(b.part_b_claims, 0)                AS part_b_claims,
        COALESCE(b.part_b_beneficiaries, 0)         AS part_b_beneficiaries,
        COALESCE(b.part_b_dosage_units, 0)          AS part_b_dosage_units,
        b.part_b_avg_cost_per_claim,
        b.part_b_avg_cost_per_bene,
        COALESCE(d.part_d_spending, 0) + COALESCE(b.part_b_spending, 0) AS total_spending,
        COALESCE(d.part_d_beneficiaries, 0) + COALESCE(b.part_b_beneficiaries, 0) AS total_beneficiaries
    FROM part_d d
    FULL OUTER JOIN part_b b
        ON LOWER(d.generic_name) = LOWER(b.generic_name)
        AND d._source_year = b._source_year
)

SELECT
    gen_random_uuid()                           AS id,
    c.generic_name,
    c.brand_name,
    c.manufacturer_name,
    c.hcpcs_code,
    c._source_year,
    c.part_d_spending,
    c.part_d_claims,
    c.part_d_beneficiaries,
    c.part_d_dosage_units,
    c.part_d_avg_cost_per_claim,
    c.part_d_avg_cost_per_bene,
    c.part_b_spending,
    c.part_b_claims,
    c.part_b_beneficiaries,
    c.part_b_dosage_units,
    c.part_b_avg_cost_per_claim,
    c.part_b_avg_cost_per_bene,
    c.total_spending,
    c.total_beneficiaries,
    CASE
        WHEN c.total_spending > 0 AND c.total_beneficiaries > 0
        THEN c.total_spending / c.total_beneficiaries
        ELSE NULL
    END                                         AS avg_spending_per_beneficiary,
    -- molecule_id: tiered linking strategy
    --   Tier 1 (Part D generic names): alias → RxNorm → first-token alias
    --   Tier 2 (Part B HCPCS codes):   hcpcs_molecule_bridge
    COALESCE(
        -- Tier 1a: exact alias match on full stripped generic_name (Part D / both)
        (
            SELECT ma.molecule_id
            FROM mol_silver.molecule_aliases ma
            WHERE LOWER(REGEXP_REPLACE(c.generic_name, '[^a-zA-Z0-9]', '', 'g'))
                = ma.alias_name_normalized
            LIMIT 1
        ),
        -- Tier 1b: RxNorm name match (handles CMS multi-word generics not in aliases)
        (
            SELECT DISTINCT rx.molecule_id
            FROM mol_silver.rxnorm_concepts rx
            WHERE rx.molecule_id IS NOT NULL
              AND LOWER(rx.name) = LOWER(c.generic_name)
            LIMIT 1
        ),
        -- Tier 1c: first-token alias (salt forms: "paclitaxel protein-bound" → "paclitaxel")
        (
            SELECT ma.molecule_id
            FROM mol_silver.molecule_aliases ma
            WHERE LENGTH(SPLIT_PART(c.generic_name, ' ', 1)) >= 4
              AND LOWER(REGEXP_REPLACE(
                      SPLIT_PART(c.generic_name, ' ', 1),
                      '[^a-zA-Z0-9]', '', 'g'
                  )) = ma.alias_name_normalized
            LIMIT 1
        ),
        -- Tier 2: HCPCS bridge for Part B codes (c.hcpcs_code populated from part_b CTE)
        (
            SELECT hb.molecule_id
            FROM mol_silver.hcpcs_molecule_bridge hb
            WHERE c.hcpcs_code IS NOT NULL
              AND LOWER(hb.hcpcs_code) = LOWER(c.hcpcs_code)
            ORDER BY hb.confidence DESC
            LIMIT 1
        )
    )                                           AS molecule_id,
    NOW()                                       AS created_at,
    NOW()                                       AS updated_at
FROM combined c
WHERE c.generic_name IS NOT NULL;
