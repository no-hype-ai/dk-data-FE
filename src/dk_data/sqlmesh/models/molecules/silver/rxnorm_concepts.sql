-- SQLMesh Model: Silver RxNorm Concepts
-- Promotes mol_bronze.rxnorm into mol_silver.identifier_mappings (rxcui entries)
-- and also provides a standalone mol_silver.rxnorm_concepts table for
-- downstream use (drug utilization joins, HCS bridge tables).
--
-- Entity linking: name match → mol_silver.molecules, then alias fallback.
-- RxNorm CUIs are the definitive US drug identifiers for prescriptions.

MODEL (
    name mol_silver.rxnorm_concepts,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key rxcui
    ),
    cron '@weekly',
    grain rxcui,
    audits (
        not_null(columns := (rxcui)),
        unique_values(columns := (rxcui))
    )
);

SELECT
    gen_random_uuid()                                           AS id,
    -- Molecule linkage: name → mol_silver.molecules, fallback to alias table
    COALESCE(m_name.molecule_id, m_alias.molecule_id)                            AS molecule_id,
    b.rxcui,
    b.name,
    b.tty,
    b.synonym,
    b.suppress,
    b.ingredients,
    b.brand_names,
    b.ndc_codes,
    b.atc_codes,
    b.drug_classes,
    'rxnorm'                                                   AS source,
    b.source_updated_at,
    NOW()                                                      AS created_at

FROM mol_bronze.rxnorm b
-- Link via canonical name (case-insensitive); molecules.canonical_name is unique
LEFT JOIN mol_silver.molecules m_name
       ON b.name IS NOT NULL
      AND LOWER(m_name.canonical_name) = LOWER(b.name)
-- Fallback: alias table — molecule_aliases has 375+ dup alias_name_normalized rows,
-- so pick one molecule_id per alias via DISTINCT ON to prevent fan-out.
LEFT JOIN (
    SELECT DISTINCT ON (alias_name_normalized)
        alias_name_normalized, molecule_id
    FROM mol_silver.molecule_aliases
    ORDER BY alias_name_normalized, molecule_id
) ma ON m_name.molecule_id IS NULL
      AND b.name IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.name, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
LEFT JOIN mol_silver.molecules m_alias ON m_alias.molecule_id = ma.molecule_id

WHERE b.rxcui IS NOT NULL;
