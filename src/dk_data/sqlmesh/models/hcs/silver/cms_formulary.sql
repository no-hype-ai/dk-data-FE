-- SQLMesh Model: Silver CMS Part D Formulary
-- Typed pass-through of CMS Part D formulary data from hcs_bronze.cms_formulary.
-- Links drugs to molecules via rxcui → mol_silver.identifier_mappings (identifier_type='rxcui'),
-- falling back to mol_silver.molecule_aliases when no identifier_mappings entry exists.
-- Note: mol_silver.molecules has no rxcui column; rxcui→molecule_id resolution requires
-- the identifier_mappings table (populated from drug_labels.rxcui via OpenFDA).
-- Consumers: drug_utilization, part_d_prescribing, market access analysis.
-- Part of: issue #172 H3, #173 C4

MODEL (
    name hcs_silver.cms_formulary,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (formulary_id, rxcui))
    ),
    grain (formulary_id, rxcui)
);

SELECT DISTINCT ON (b.formulary_id, b.rxcui)
    gen_random_uuid()               AS id,
    b.formulary_id,
    b.rxcui,
    b.tier_level,
    b.prior_auth,
    b.step_therapy,
    b.quantity_limit,

    -- Molecule linkage via RxNorm CUI
    COALESCE(im.molecule_id, m_alias.molecule_id) AS molecule_id,

    b.source,
    b.ingested_at,
    b.ingested_at                   AS source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_formulary b

-- Primary: rxcui → identifier_mappings (populated from drug_labels.rxcui JSONB via OpenFDA)
LEFT JOIN mol_silver.identifier_mappings im
       ON b.rxcui IS NOT NULL
      AND im.identifier_type = 'rxcui'
      AND im.identifier_value = b.rxcui::TEXT

-- Fallback: rxcui as alias_name in molecule_aliases (edge case)
LEFT JOIN mol_silver.molecule_aliases ma
       ON im.molecule_id IS NULL
      AND b.rxcui IS NOT NULL
      AND ma.alias_name = b.rxcui::TEXT
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id

WHERE b.formulary_id IS NOT NULL
  AND b.rxcui IS NOT NULL
ORDER BY b.formulary_id, b.rxcui, COALESCE(im.molecule_id, m_alias.molecule_id) NULLS LAST
