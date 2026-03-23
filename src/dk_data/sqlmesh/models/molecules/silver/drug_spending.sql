-- SQLMesh Model: Silver Drug Spending
-- Promotes CMS Medicare Part B/D spending from mol_bronze.cms_medicare
-- into mol_silver.drug_spending with molecule-level linkage.
-- Entity linking: LEFT JOIN mol_silver.molecules on generic_name, brand_name as fallback.
-- FULL refresh ensures molecule_id is always current when new molecules are added.
-- Part of: Tier 4 gap fix — was blocked by enabled=false cron + missing silver model

MODEL (
    name mol_silver.drug_spending,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (generic_name, program, year))
    )
);

SELECT
    gen_random_uuid()                   AS spending_id,
    COALESCE(m_gen.molecule_id, m_brand.molecule_id) AS molecule_id,
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
    'cms_medicare'                      AS source,
    b.ingested_at                       AS created_at

FROM mol_bronze.cms_medicare b
LEFT JOIN mol_silver.molecules m_gen
       ON LOWER(m_gen.canonical_name) = LOWER(b.generic_name)
LEFT JOIN mol_silver.molecules m_brand
       ON m_gen.molecule_id IS NULL
      AND b.brand_name IS NOT NULL
      AND LOWER(m_brand.canonical_name) = LOWER(b.brand_name)
WHERE b.generic_name IS NOT NULL
  AND b.year IS NOT NULL;
