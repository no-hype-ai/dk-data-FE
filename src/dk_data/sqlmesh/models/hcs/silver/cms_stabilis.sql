-- SQLMesh Model: Silver CMS Stabilis IV Drug Compatibility
-- IV drug compatibility and stability reference data with molecule linkage.
-- Grain: (drug_a, drug_b)
--
-- Linkage strategy (both drugs):
--   Normalized drug name → mol_silver.molecule_aliases (alias_name_normalized match, LIMIT 1)
--   Prevents fan-out: each drug gets at most one molecule_id via LATERAL subquery.

MODEL (
    name hcs_silver.cms_stabilis,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (drug_a, drug_b))
    ),
    grain (drug_a, drug_b)
);

SELECT DISTINCT ON (b.drug_a, b.drug_b)
    gen_random_uuid()               AS id,
    b.drug_a,
    b.drug_b,
    b.compatibility,
    b.solvent,
    b.concentration,
    b.reference,

    -- Molecule linkage for drug_a
    mol_a.molecule_id               AS molecule_id_a,
    -- Molecule linkage for drug_b
    mol_b.molecule_id               AS molecule_id_b,

    b.source,
    b.ingested_at,
    b.ingested_at                   AS source_updated_at,
    NOW()                           AS created_at

FROM hcs_bronze.cms_stabilis b

-- Drug A → molecule_aliases (normalized name, LIMIT 1 prevents fan-out)
LEFT JOIN LATERAL (
    SELECT ma.molecule_id
    FROM mol_silver.molecule_aliases ma
    WHERE b.drug_a IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.drug_a, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
    ORDER BY ma.molecule_id
    LIMIT 1
) mol_a ON TRUE

-- Drug B → molecule_aliases (normalized name, LIMIT 1 prevents fan-out)
LEFT JOIN LATERAL (
    SELECT ma.molecule_id
    FROM mol_silver.molecule_aliases ma
    WHERE b.drug_b IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.drug_b, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
    ORDER BY ma.molecule_id
    LIMIT 1
) mol_b ON TRUE

WHERE b.drug_a IS NOT NULL
  AND b.drug_b IS NOT NULL
ORDER BY b.drug_a, b.drug_b, b.ingested_at DESC
