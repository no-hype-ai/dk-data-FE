-- SQLMesh Model: Silver Therapeutic Target Database (TTD)
-- Promotes mol_bronze.ttd into mol_silver.ttd with molecule_id linkage.
-- TTD contains drug–target interaction data: drugs, targets, clinical status, InChI keys.
-- Entity linking: inchi_key → mol_silver.molecules; fallback: drug_name → canonical_name/alias.

MODEL (
    name mol_silver.ttd,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (ttd_id))
    ),
    grain ttd_id
);

SELECT DISTINCT ON (b.ttd_id)
    gen_random_uuid()                                           AS id,
    COALESCE(m_ik.molecule_id, m_exact.molecule_id,
             m_alias.molecule_id, m_token.molecule_id)         AS molecule_id,
    b.ttd_id,
    b.entity_type,
    b.drug_name,
    b.drug_type,
    b.drug_status,
    b.cas_number,
    b.inchi_key,
    b.smiles,
    b.pubchem_cid,
    b.target_name,
    b.target_type,
    b.uniprot_id,
    b.targets,
    b.drug_class,
    b.synonyms,
    'ttd'                                                       AS source,
    b.source_updated_at,
    NOW()                                                       AS created_at

FROM mol_bronze.ttd b
-- Primary: inchi_key exact match
LEFT JOIN mol_silver.molecules m_ik
       ON b.inchi_key IS NOT NULL AND m_ik.inchi_key = b.inchi_key
-- Fallback: canonical_name match on drug_name
LEFT JOIN mol_silver.molecules m_exact
       ON m_ik.molecule_id IS NULL
      AND b.drug_name IS NOT NULL
      AND LOWER(m_exact.canonical_name) = LOWER(b.drug_name)
-- Fallback 2: full drug_name stripped → alias_name_normalized
--   Catches drugs where spaces are removed: "imatinibmesylate" matches stored alias
LEFT JOIN mol_silver.molecule_aliases ma
       ON m_ik.molecule_id IS NULL
      AND m_exact.molecule_id IS NULL
      AND b.drug_name IS NOT NULL
      AND LOWER(REGEXP_REPLACE(b.drug_name, '[^a-zA-Z0-9]', '', 'g'))
          = ma.alias_name_normalized
LEFT JOIN mol_silver.molecules m_alias
       ON m_alias.molecule_id = ma.molecule_id
-- Fallback 3: first-token alias match for salt forms
--   "Imatinib Mesylate" → first token "imatinib" → alias "imatinib"
--   Minimum 4 chars to prevent short-token false positives
LEFT JOIN mol_silver.molecule_aliases ma_tok
       ON m_ik.molecule_id IS NULL
      AND m_exact.molecule_id IS NULL
      AND m_alias.molecule_id IS NULL
      AND b.drug_name IS NOT NULL
      AND LENGTH(SPLIT_PART(b.drug_name, ' ', 1)) >= 4
      AND LOWER(REGEXP_REPLACE(
              SPLIT_PART(b.drug_name, ' ', 1),
              '[^a-zA-Z0-9]', '', 'g'
          )) = ma_tok.alias_name_normalized
LEFT JOIN mol_silver.molecules m_token
       ON m_token.molecule_id = ma_tok.molecule_id
WHERE b.ttd_id IS NOT NULL
ORDER BY b.ttd_id,
         COALESCE(m_ik.molecule_id, m_exact.molecule_id,
                  m_alias.molecule_id, m_token.molecule_id) NULLS LAST;
