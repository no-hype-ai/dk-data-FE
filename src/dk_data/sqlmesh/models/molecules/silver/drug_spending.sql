-- SQLMesh Model: Silver Drug Spending
-- Unified Medicare Part D + Part B spending per molecule, linked to mol_silver.molecules.
-- Feature: 019-cms-puf-platform-reconciliation (T025)
--
-- Grain: (generic_name, program, _source_year)
-- Sources: hcs_bronze.cms_part_d_spending, hcs_bronze.cms_part_b_spending, mol_silver.molecules

MODEL (
    name mol_silver.drug_spending,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (generic_name, program, _source_year))
    ),
    grain (generic_name, program, _source_year)
);

WITH part_d AS (
    SELECT
        gnrc_name                           AS generic_name,
        brnd_name                           AS brand_name,
        'part_d'                            AS program,
        _source_year,
        SUM(tot_drug_cst)                   AS total_spending,
        SUM(tot_clms)                       AS total_claims,
        SUM(tot_benes)                      AS total_beneficiaries,
        AVG(avg_spnd_per_clm)               AS avg_spending_per_claim,
        AVG(avg_spnd_per_bene)              AS avg_spending_per_beneficiary
    FROM hcs_bronze.cms_part_d_spending
    WHERE gnrc_name IS NOT NULL
    GROUP BY gnrc_name, brnd_name, _source_year
),

part_b AS (
    SELECT
        hcpcs_desc                          AS generic_name,
        NULL::TEXT                          AS brand_name,
        'part_b'                            AS program,
        _source_year,
        SUM(tot_mdcr_pymt_amt)              AS total_spending,
        SUM(tot_srvcs)                      AS total_claims,
        SUM(tot_benes)                      AS total_beneficiaries,
        AVG(avg_mdcr_pymt_amt)              AS avg_spending_per_claim,
        NULL::NUMERIC                       AS avg_spending_per_beneficiary
    FROM hcs_bronze.cms_part_b_spending
    WHERE hcpcs_desc IS NOT NULL
    GROUP BY hcpcs_desc, _source_year
),

combined AS (
    SELECT * FROM part_d
    UNION ALL
    SELECT * FROM part_b
),

-- Link to molecules via name match
linked AS (
    SELECT
        c.generic_name,
        c.brand_name,
        c.program,
        c._source_year,
        c.total_spending,
        c.total_claims,
        c.total_beneficiaries,
        c.avg_spending_per_claim,
        c.avg_spending_per_beneficiary,
        -- Try exact canonical name match first, then brand name fallback
        COALESCE(
            m_exact.molecule_id,
            m_brand.molecule_id
        )                                   AS molecule_id,
        CASE
            WHEN m_exact.molecule_id IS NOT NULL THEN 'exact_canonical'
            WHEN m_brand.molecule_id IS NOT NULL THEN 'brand_name'
            ELSE 'unlinked'
        END                                 AS link_strategy
    FROM combined c
    LEFT JOIN mol_silver.molecules m_exact
        ON LOWER(c.generic_name) = LOWER(m_exact.canonical_name)
    LEFT JOIN mol_silver.molecules m_brand
        ON LOWER(c.brand_name) = LOWER(m_brand.canonical_name)
        AND c.brand_name IS NOT NULL
)

SELECT
    gen_random_uuid()                       AS id,
    generic_name,
    brand_name,
    program,
    _source_year,
    molecule_id,
    link_strategy,
    total_spending,
    total_claims,
    total_beneficiaries,
    avg_spending_per_claim,
    avg_spending_per_beneficiary,
    NOW()                                   AS created_at,
    NOW()                                   AS updated_at
FROM linked;
