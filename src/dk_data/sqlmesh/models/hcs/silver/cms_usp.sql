-- SQLMesh Model: Silver CMS USP Drug Classification
-- USP therapeutic category and class data with molecule linkage.
-- Grain: rxcui
--
-- Linkage strategy (tiered):
--   Tier 1: rxcui → mol_silver.molecule_identifiers (source='rxnorm') — LATERAL LIMIT 1
--   Tier 2: branded_name → mol_silver.molecule_names (normalized_name) — LATERAL LIMIT 1

MODEL (
    name hcs_silver.cms_usp,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (rxcui))
    ),
    grain rxcui
);

SELECT DISTINCT ON (b.rxcui)
    gen_random_uuid()               AS id,
    b.rxcui,
    b.tty,
    b.branded_name,
    b.usp_category,
    b.usp_class,

    -- Molecule linkage
    COALESCE(mol_rxcui.molecule_id, mol_alias.molecule_id) AS molecule_id,

    b.source,
    b.ingested_at,
    b.ingested_at                   AS source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_usp b

-- Tier 1: rxcui → molecule_identifiers (source='rxnorm'; multiple molecules may share rxcui; take first)
LEFT JOIN LATERAL (
    SELECT mi.molecule_id
    FROM mol_silver.molecule_identifiers mi
    WHERE mi.source = 'rxnorm'
      AND mi.identifier = b.rxcui
    ORDER BY mi.molecule_id
    LIMIT 1
) mol_rxcui ON TRUE

-- Tier 2: branded_name → molecule_names (when rxcui linkage returns nothing)
LEFT JOIN LATERAL (
    SELECT mn.molecule_id
    FROM mol_silver.molecule_names mn
    WHERE mol_rxcui.molecule_id IS NULL
      AND b.branded_name IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.branded_name, '[^a-zA-Z0-9]', '', 'g')) = mn.normalized_name
    ORDER BY mn.molecule_id
    LIMIT 1
) mol_alias ON TRUE

WHERE b.rxcui IS NOT NULL
ORDER BY b.rxcui, b.ingested_at DESC
