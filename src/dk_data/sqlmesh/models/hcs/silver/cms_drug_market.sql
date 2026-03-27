-- SQLMesh Model: Silver CMS Drug Market
-- Aggregates Medicare Part D and Part B drug spending into unified drug market view.
-- Feature: 019-cms-puf-platform-reconciliation (T013)
--
-- Grain: (generic_name, _source_year)
-- Sources: hcs_bronze.cms_part_d_spending, hcs_bronze.cms_part_b_spending

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
    SELECT
        gnrc_name                           AS generic_name,
        brnd_name                           AS brand_name,
        mftr_name                           AS manufacturer_name,
        _source_year,
        SUM(tot_drug_cst)                   AS part_d_spending,
        SUM(tot_clms)                       AS part_d_claims,
        SUM(tot_benes)                      AS part_d_beneficiaries,
        SUM(tot_30day_fills)                AS part_d_30day_fills,
        AVG(avg_spnd_per_clm)               AS part_d_avg_cost_per_claim,
        AVG(avg_spnd_per_bene)              AS part_d_avg_cost_per_bene
    FROM hcs_bronze.cms_part_d_spending
    WHERE generic_name IS NOT NULL
    GROUP BY gnrc_name, brnd_name, mftr_name, _source_year
),

part_b AS (
    SELECT
        hcpcs_desc                          AS generic_name,
        hcpcs_cd                            AS hcpcs_code,
        _source_year,
        SUM(tot_mdcr_pymt_amt)              AS part_b_spending,
        SUM(tot_srvcs)                      AS part_b_services,
        SUM(tot_benes)                      AS part_b_beneficiaries,
        AVG(avg_mdcr_pymt_amt)              AS part_b_avg_payment
    FROM hcs_bronze.cms_part_b_spending
    WHERE hcpcs_desc IS NOT NULL
    GROUP BY hcpcs_desc, hcpcs_cd, _source_year
),

combined AS (
    SELECT
        COALESCE(d.generic_name, b.generic_name)    AS generic_name,
        d.brand_name,
        d.manufacturer_name,
        b.hcpcs_code,
        COALESCE(d._source_year, b._source_year)    AS _source_year,
        COALESCE(d.part_d_spending, 0)              AS part_d_spending,
        COALESCE(d.part_d_claims, 0)                AS part_d_claims,
        COALESCE(d.part_d_beneficiaries, 0)         AS part_d_beneficiaries,
        COALESCE(d.part_d_30day_fills, 0)           AS part_d_30day_fills,
        d.part_d_avg_cost_per_claim,
        d.part_d_avg_cost_per_bene,
        COALESCE(b.part_b_spending, 0)              AS part_b_spending,
        COALESCE(b.part_b_services, 0)              AS part_b_services,
        COALESCE(b.part_b_beneficiaries, 0)         AS part_b_beneficiaries,
        b.part_b_avg_payment,
        COALESCE(d.part_d_spending, 0) + COALESCE(b.part_b_spending, 0) AS total_spending,
        COALESCE(d.part_d_beneficiaries, 0) + COALESCE(b.part_b_beneficiaries, 0) AS total_beneficiaries
    FROM part_d d
    FULL OUTER JOIN part_b b
        ON LOWER(d.generic_name) = LOWER(b.generic_name)
        AND d._source_year = b._source_year
)

SELECT
    gen_random_uuid()                       AS id,
    generic_name,
    brand_name,
    manufacturer_name,
    hcpcs_code,
    _source_year,
    part_d_spending,
    part_d_claims,
    part_d_beneficiaries,
    part_d_30day_fills,
    part_d_avg_cost_per_claim,
    part_d_avg_cost_per_bene,
    part_b_spending,
    part_b_services,
    part_b_beneficiaries,
    part_b_avg_payment,
    total_spending,
    total_beneficiaries,
    CASE
        WHEN total_spending > 0 AND total_beneficiaries > 0
        THEN total_spending / total_beneficiaries
        ELSE NULL
    END                                     AS avg_spending_per_beneficiary,
    NOW()                                   AS created_at,
    NOW()                                   AS updated_at
FROM combined
WHERE generic_name IS NOT NULL;
