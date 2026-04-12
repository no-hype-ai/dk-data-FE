-- SQLMesh Model: Silver NICE HTA Decisions
-- Typed pass-through of NICE health technology assessments from mol_bronze.nice_hta,
-- enriched with molecule_id linkage via drug_name → molecule_aliases.
-- Consumers: regulatory_timeline gold, market access analysis, lifecycle evidence.
-- Part of: issue #172 H2

MODEL (
    name mol_silver.nice_hta,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key guidance_id
    ),
    cron '@weekly',
    audits (
        not_null(columns := (guidance_id, source))
    ),
    grain guidance_id,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (b.guidance_id)
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

LEFT JOIN mol_silver.molecule_names ma
       ON m_name.molecule_id IS NULL
      AND b.drug_name IS NOT NULL
      AND LOWER(ma.display_name) = LOWER(b.drug_name)
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id

WHERE b.guidance_id IS NOT NULL
ORDER BY b.guidance_id, COALESCE(m_name.molecule_id, m_alias.molecule_id) NULLS LAST
