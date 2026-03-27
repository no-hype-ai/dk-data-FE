-- SQLMesh Model: Silver IMGT Antibody Structures
-- Promotes mol_bronze.imgt into mol_silver.imgt with molecule_id linkage.
-- IMGT/3Dstructure-DB: antibody/biologic structural data (PDB, chains, species).
-- Critical for biologic (mAb/ADC) characterisation during assessment.
-- Entity linking: drug_name → canonical_name/alias; fallback: uniprot_id → targets.

MODEL (
    name mol_silver.imgt,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (pdb_code))
    ),
    grain pdb_code
);

SELECT
    gen_random_uuid()                                           AS id,
    COALESCE(m_exact.molecule_id, m_alias.molecule_id,
             m_uniprot.molecule_id)                            AS molecule_id,
    b.pdb_code,
    b.molecule_name,
    b.species,
    b.receptor_type,
    b.chains,
    b.heavy_chain_subgroup,
    b.light_chain_subgroup,
    b.light_chain_type,
    b.resolution,
    b.experimental_method,
    b.uniprot_id,
    b.drug_name,
    'imgt'                                                      AS source,
    b.source_updated_at,
    NOW()                                                       AS created_at

FROM mol_bronze.imgt b
-- Primary: drug_name → canonical_name
LEFT JOIN mol_silver.molecules m_exact
       ON b.drug_name IS NOT NULL
      AND LOWER(m_exact.canonical_name) = LOWER(b.drug_name)
-- Fallback: alias match on drug_name
LEFT JOIN mol_silver.molecule_aliases ma
       ON m_exact.molecule_id IS NULL
      AND b.drug_name IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.drug_name, '[^a-zA-Z0-9]', '', 'g'))
          = ma.alias_name_normalized
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id
-- Fallback: via uniprot_id → targets → molecules
LEFT JOIN mol_silver.targets t
       ON m_exact.molecule_id IS NULL
      AND m_alias.molecule_id IS NULL
      AND b.uniprot_id IS NOT NULL
      AND t.uniprot_id = b.uniprot_id
LEFT JOIN mol_silver.molecules m_uniprot
       ON m_uniprot.molecule_id = t.molecule_id
WHERE b.pdb_code IS NOT NULL;
