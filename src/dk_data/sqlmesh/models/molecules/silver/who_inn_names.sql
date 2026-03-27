-- SQLMesh Model: Silver WHO INN Names
-- Promotes mol_bronze.who_inn into mol_silver.who_inn_names with molecule_id linkage.
-- WHO INNs are the authoritative international nonproprietary names for active
-- pharmaceutical ingredients — the global equivalent of USAN (US Adopted Names).
--
-- Entity linking: inchi_key → mol_silver.molecules (when available), then name match.
-- Feeds downstream: mol_silver.molecule_aliases (inn alias type), mol_silver.identifier_mappings (inn_name).

MODEL (
    name mol_silver.who_inn_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key inn_name
    ),
    cron '@weekly',
    grain inn_name,
    audits (
        not_null(columns := (inn_name)),
        unique_values(columns := (inn_name))
    )
);

SELECT
    gen_random_uuid()                                           AS id,
    COALESCE(m_ik.id, m_name.id, m_alias.id)                  AS molecule_id,
    b.inn_name,
    b.inn_latin,
    b.inn_list_number,
    b.inn_year,
    b.cas_number,
    b.molecular_formula,
    b.smiles,
    b.inchi_key,
    b.inn_stem,
    b.stem_definition,
    b.research_codes,
    b.synonyms,
    b.status,
    'who_inn'                                                  AS source,
    b.source_updated_at,
    NOW()                                                      AS created_at

FROM mol_bronze.who_inn b
-- Link via inchi_key (most reliable when available)
LEFT JOIN mol_silver.molecules m_ik
       ON b.inchi_key IS NOT NULL
      AND m_ik.inchi_key = b.inchi_key
-- Fallback: canonical name match
LEFT JOIN mol_silver.molecules m_name
       ON m_ik.id IS NULL
      AND b.inn_name IS NOT NULL
      AND LOWER(m_name.canonical_name) = LOWER(b.inn_name)
-- Fallback: alias table
LEFT JOIN mol_silver.molecule_aliases ma
       ON m_ik.id IS NULL AND m_name.id IS NULL
      AND b.inn_name IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.inn_name, '[^a-zA-Z0-9]', '', 'g')) = ma.alias_name_normalized
LEFT JOIN mol_silver.molecules m_alias ON m_alias.id = ma.molecule_id

WHERE b.inn_name IS NOT NULL;
