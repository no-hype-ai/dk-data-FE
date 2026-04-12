-- SQLMesh Model: Silver CMS NDC Directory
-- Typed pass-through of CMS NDC product records from hcs_bronze.cms_ndc.
-- Links drugs to molecules via nonproprietary_name → mol_silver.molecules (canonical_name),
-- falling back to mol_silver.molecule_names when direct match is unavailable.
-- Consumers: drug_utilization, formulary analysis, market access, Part D spend.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_ndc,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key product_ndc
    ),
    cron '@monthly',
    audits (
        not_null(columns := (product_ndc))
    ),
    grain product_ndc,
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

SELECT DISTINCT ON (b.product_ndc)
    gen_random_uuid()               AS id,
    b.product_ndc,
    b.proprietary_name,
    b.nonproprietary_name,
    b.labeler_name,
    b.dosage_form,
    b.route,
    b.product_type,

    -- Molecule linkage via nonproprietary (generic) drug name
    COALESCE(m_name.molecule_id, m_alias.molecule_id) AS molecule_id,

    b.source,
    b.ingested_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_ndc b

-- Primary: match nonproprietary_name against canonical molecule name
LEFT JOIN mol_silver.molecules m_name
       ON b.nonproprietary_name IS NOT NULL
      AND LOWER(m_name.canonical_name) = LOWER(b.nonproprietary_name)

-- Fallback: match via molecule aliases
LEFT JOIN mol_silver.molecule_names ma
       ON m_name.molecule_id IS NULL
      AND b.nonproprietary_name IS NOT NULL
      AND LOWER(ma.display_name) = LOWER(b.nonproprietary_name)
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id

WHERE b.product_ndc IS NOT NULL
ORDER BY b.product_ndc, COALESCE(m_name.molecule_id, m_alias.molecule_id) NULLS LAST
