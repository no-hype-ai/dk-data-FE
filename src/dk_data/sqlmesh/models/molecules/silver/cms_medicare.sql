-- SQLMesh Model: Silver CMS Medicare Drug Spending
-- Typed pass-through of Medicare drug spending from mol_bronze.cms_medicare,
-- enriched with molecule_id linkage via generic_name → molecule_aliases.
-- DISTINCT ON (generic_name, program, year) applied defensively: if mol_silver.molecule_aliases
-- contains the same alias for multiple molecules the fallback JOIN would fan-out, violating grain.
-- Consumers: drug_spending silver model, market_summary gold aggregations.
-- Part of: issue #172 H2, #173 N5

MODEL (
    name mol_silver.cms_medicare,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (generic_name, source))
    ),
    grain (generic_name, program, year)
);

SELECT DISTINCT ON (b.generic_name, b.program, b.year)
    gen_random_uuid()               AS id,

    -- Molecule linkage: generic_name → canonical or alias match
    COALESCE(m_name.molecule_id, m_alias.molecule_id) AS molecule_id,

    b.generic_name,
    b.brand_name,
    b.drug_code,
    b.program,
    b.year,
    b.total_supply_days,
    b.total_claims,
    b.total_beneficiaries,
    b.total_spending,
    b.avg_cost_per_claim,
    b.avg_cost_per_day,
    b.avg_cost_per_beneficiary,

    b.source,
    b.source_updated_at,
    NOW()                           AS created_at

FROM mol_bronze.cms_medicare b

-- Link via canonical name
LEFT JOIN mol_silver.molecules m_name
       ON b.generic_name IS NOT NULL
      AND LOWER(m_name.canonical_name) = LOWER(b.generic_name)

-- Fallback: via alias
LEFT JOIN mol_silver.molecule_aliases ma
       ON m_name.molecule_id IS NULL
      AND b.generic_name IS NOT NULL
      AND LOWER(ma.alias_name) = LOWER(b.generic_name)
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id

WHERE b.generic_name IS NOT NULL
ORDER BY b.generic_name, b.program, b.year,
         COALESCE(m_name.molecule_id, m_alias.molecule_id) NULLS LAST
