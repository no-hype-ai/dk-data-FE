-- SQLMesh Model: Silver NICE HTA Decisions
-- Typed pass-through of NICE health technology assessments from mol_bronze.nice_hta,
-- enriched with molecule_id linkage via drug_name → molecule_aliases.
-- Consumers: regulatory_timeline gold, market access analysis, lifecycle evidence.
-- Part of: issue #172 H2

MODEL (
    name mol_silver.nice_hta,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (guidance_id, source))
    ),
    grain guidance_id
);

SELECT
    gen_random_uuid()               AS id,
    b.guidance_id,
    b.title,
    b.guidance_type,
    b.drug_name,
    b.decision,
    b.recommendation,
    b.icer_value,
    b.published_date,
    b.last_updated_date,

    -- Molecule linkage via drug_name → canonical or alias
    COALESCE(m_name.molecule_id, m_alias.molecule_id) AS molecule_id,

    b.source,
    b.source_updated_at,
    NOW()                           AS created_at

FROM mol_bronze.nice_hta b

LEFT JOIN mol_silver.molecules m_name
       ON b.drug_name IS NOT NULL
      AND LOWER(m_name.canonical_name) = LOWER(b.drug_name)

LEFT JOIN mol_silver.molecule_aliases ma
       ON m_name.molecule_id IS NULL
      AND b.drug_name IS NOT NULL
      AND LOWER(ma.alias_name) = LOWER(b.drug_name)
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id

WHERE b.guidance_id IS NOT NULL
