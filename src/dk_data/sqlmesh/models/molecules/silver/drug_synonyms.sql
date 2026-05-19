-- SQLMesh Model: Silver Drug Synonyms (WHO INN)
-- Promotes mol_bronze.who_inn into mol_silver.drug_synonyms with molecule_id linkage.
-- WHO International Nonproprietary Names (INN) are the official generic drug names.
-- Entity linking: inchi_key → canonical_name → normalized_name (stripped).

MODEL (
    name mol_silver.drug_synonyms,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key inn_name
    ),
    cron '@monthly',
    audits (
        not_null(columns := (inn_name))
    ),
    grain inn_name
);

SELECT
    gen_random_uuid()                                               AS id,
    COALESCE(m_ik.molecule_id, m_name.molecule_id, m_alias.molecule_id) AS molecule_id,
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
    'who_inn'                                                       AS source,
    b.ingested_at,
    b.source_updated_at,
    NOW()                                                           AS created_at

FROM mol_bronze.who_inn b
LEFT JOIN mol_silver.molecules m_ik
       ON b.inchi_key IS NOT NULL AND m_ik.inchi_key = b.inchi_key
LEFT JOIN mol_silver.molecules m_name
       ON m_ik.molecule_id IS NULL
      AND b.inn_name IS NOT NULL
      AND LOWER(m_name.canonical_name) = LOWER(b.inn_name)
-- Fallback: alias table — deduplicated to prevent fan-out from duplicate normalized_name rows
LEFT JOIN (
    SELECT DISTINCT ON (normalized_name)
        normalized_name, molecule_id
    FROM mol_silver.molecule_names
    ORDER BY normalized_name, molecule_id
) ma ON m_ik.molecule_id IS NULL AND m_name.molecule_id IS NULL
      AND b.inn_name IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.inn_name, '[^a-zA-Z0-9]', '', 'g')) = ma.normalized_name
LEFT JOIN mol_silver.molecules m_alias ON m_alias.molecule_id = ma.molecule_id
WHERE b.inn_name IS NOT NULL;
