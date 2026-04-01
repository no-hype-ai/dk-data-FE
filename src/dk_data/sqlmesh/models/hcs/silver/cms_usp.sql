-- SQLMesh Model: Silver CMS USP Drug Classification
-- USP therapeutic category and class data with molecule linkage.
-- Grain: rxcui
--
-- Linkage strategy (tiered):
--   Tier 1: rxcui → mol_silver.identifier_mappings (identifier_type='rxcui') — LATERAL LIMIT 1
--   Tier 2: branded_name → mol_silver.molecule_aliases (normalized) — LATERAL LIMIT 1

MODEL (
    name hcs_silver.cms_usp,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (rxcui))
    ),
    grain rxcui
);

SELECT
    gen_random_uuid()               AS id,
    b.rxcui,
    b.tty,
    b.branded_name,
    b.usp_category,
    b.usp_class,

    -- Molecule linkage
    COALESCE(mol_rxcui.molecule_id, mol_alias.molecule_id) AS molecule_id,

    b.source,
    b.ingested_at                   AS source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_usp b

-- Tier 1: rxcui → identifier_mappings (multiple molecules may share rxcui; take first)
LEFT JOIN LATERAL (
    SELECT im.molecule_id
    FROM mol_silver.identifier_mappings im
    WHERE im.identifier_type = 'rxcui'
      AND im.identifier_value = b.rxcui
    ORDER BY im.molecule_id
    LIMIT 1
) mol_rxcui ON TRUE

-- Tier 2: branded_name → molecule_aliases (when rxcui linkage returns nothing)
LEFT JOIN LATERAL (
    SELECT ma.molecule_id
    FROM mol_silver.molecule_aliases ma
    WHERE mol_rxcui.molecule_id IS NULL
      AND b.branded_name IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.branded_name, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
    ORDER BY ma.molecule_id
    LIMIT 1
) mol_alias ON TRUE

WHERE b.rxcui IS NOT NULL
