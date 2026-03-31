-- SQLMesh Model: Silver CMS Part D Formulary
-- Typed pass-through of CMS Part D formulary data from hcs_bronze.cms_formulary.
-- Links drugs to molecules via rxcui → mol_silver.molecules (rxcui column),
-- falling back to mol_silver.molecule_aliases when direct match is unavailable.
-- Consumers: drug_utilization, part_d_prescribing, market access analysis.
-- Part of: issue #172 H3

MODEL (
    name hcs_silver.cms_formulary,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (formulary_id, rxcui))
    ),
    grain (formulary_id, rxcui)
);

SELECT
    gen_random_uuid()               AS id,
    b.formulary_id,
    b.rxcui,
    b.tier_level,
    b.prior_auth,
    b.step_therapy,
    b.quantity_limit,

    -- Molecule linkage via RxNorm CUI
    COALESCE(m_rxcui.molecule_id, m_alias.molecule_id) AS molecule_id,

    b.source,
    b.source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_formulary b

-- Primary: match on rxcui stored in mol_silver.molecules
LEFT JOIN mol_silver.molecules m_rxcui
       ON b.rxcui IS NOT NULL
      AND m_rxcui.rxcui = b.rxcui

-- Fallback: mol_silver.molecule_aliases keyed on rxcui as alias
LEFT JOIN mol_silver.molecule_aliases ma
       ON m_rxcui.molecule_id IS NULL
      AND b.rxcui IS NOT NULL
      AND ma.alias_name = b.rxcui::TEXT
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id

WHERE b.formulary_id IS NOT NULL
  AND b.rxcui IS NOT NULL
