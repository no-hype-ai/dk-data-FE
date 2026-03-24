-- SQLMesh Model: Silver Drug Spending
-- Combines CMS Medicare Part B spending (mol_bronze.cms_medicare) and
-- CMS Part D spending (hcs_bronze.cms_part_d_spending) into a single
-- molecule-linked silver view.
-- Entity linking: LEFT JOIN mol_silver.molecules on generic_name, brand_name as fallback.
-- FULL refresh ensures molecule_id is always current when new molecules are added.

MODEL (
    name mol_silver.drug_spending,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (generic_name, program, year))
    )
);

-- CMS Part B via mol_bronze.cms_medicare (JSONB raw pipeline)
SELECT
    gen_random_uuid()                                   AS spending_id,
    COALESCE(m_gen.molecule_id, m_brand.molecule_id)    AS molecule_id,
    b.brand_name,
    b.generic_name,
    b.program,
    b.year,
    b.total_claims,
    b.total_beneficiaries,
    b.total_spending,
    b.avg_cost_per_claim,
    b.avg_cost_per_day,
    b.avg_cost_per_beneficiary,
    b.total_supply_days,
    'cms_medicare'                                      AS source,
    b.ingested_at                                       AS created_at
FROM mol_bronze.cms_medicare b
LEFT JOIN mol_silver.molecules m_gen
       ON LOWER(m_gen.canonical_name) = LOWER(b.generic_name)
LEFT JOIN mol_silver.molecules m_brand
       ON m_gen.molecule_id IS NULL
      AND b.brand_name IS NOT NULL
      AND LOWER(m_brand.canonical_name) = LOWER(b.brand_name)
WHERE b.generic_name IS NOT NULL
  AND b.year IS NOT NULL

UNION ALL

-- CMS Part D spending dashboard (hcs_bronze.cms_part_d_spending structured pipeline)
SELECT
    gen_random_uuid()                                   AS spending_id,
    COALESCE(m_gen.molecule_id, m_brand.molecule_id)    AS molecule_id,
    d.brand_name,
    d.generic_name,
    'Part D'                                            AS program,
    d.year,
    d.total_claims,
    d.total_beneficiaries,
    d.total_spending,
    d.avg_cost_per_claim,
    NULL::NUMERIC                                       AS avg_cost_per_day,
    NULL::NUMERIC                                       AS avg_cost_per_beneficiary,
    NULL::NUMERIC                                       AS total_supply_days,
    'cms_part_d_spending'                               AS source,
    d._loaded_at                                        AS created_at
FROM hcs_bronze.cms_part_d_spending d
LEFT JOIN mol_silver.molecules m_gen
       ON LOWER(m_gen.canonical_name) = LOWER(d.generic_name)
LEFT JOIN mol_silver.molecules m_brand
       ON m_gen.molecule_id IS NULL
      AND d.brand_name IS NOT NULL
      AND LOWER(m_brand.canonical_name) = LOWER(d.brand_name)
WHERE d.generic_name IS NOT NULL
  AND d.year IS NOT NULL;
