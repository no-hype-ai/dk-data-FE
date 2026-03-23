-- SQLMesh Model: Silver Molecules
-- Single source of truth for molecule identity. Populated by SQLMesh from
-- mol_bronze.chembl_molecules (primary) enriched with DrugBank and PubChem.
-- Xenon reads molecule_id via PostgREST — never writes to this table.
--
-- INCREMENTAL_BY_UNIQUE_KEY on inchi_key ensures molecule_id UUIDs are
-- generated once and remain stable across runs (existing rows are UPDATEd,
-- not replaced). New molecules appear here after their ChEMBL bronze row lands.

MODEL (
    name mol_silver.molecules,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key inchi_key
    ),
    cron '@daily',
    audits (
        not_null(columns := (inchi_key, canonical_name)),
        unique_values(columns := (inchi_key))
    ),
    grain inchi_key
);

SELECT
    gen_random_uuid()                                  AS molecule_id,
    c.inchi_key,
    c.chembl_id,
    d.drugbank_id,
    p.cid::INT                                         AS pubchem_cid,
    NULL::TEXT                                         AS rxnorm_cui,
    d.unii                                             AS unii,
    d.cas_number,
    LOWER(COALESCE(c.pref_name, d.name))               AS canonical_name,
    c.canonical_smiles,
    c.inchi,
    c.molecular_formula,
    c.molecular_weight,
    CASE LOWER(c.molecule_type)
        WHEN 'small molecule' THEN 'small_molecule'
        WHEN 'antibody'       THEN 'biologic'
        WHEN 'protein'        THEN 'biologic'
        WHEN 'oligonucleotide' THEN 'biologic'
        WHEN 'oligosaccharide' THEN 'biologic'
        WHEN 'enzyme'         THEN 'biologic'
        ELSE LOWER(REPLACE(c.molecule_type, ' ', '_'))
    END                                                AS molecule_type,
    FALSE                                              AS needs_review,
    NULL::TEXT                                         AS review_reason,
    1.0                                                AS resolution_confidence,
    NULL::TIMESTAMPTZ                                  AS reviewed_at,
    NULL::TEXT                                         AS reviewed_by,
    NOW()                                              AS created_at,
    NOW()                                              AS updated_at,
    (CASE WHEN d.drugbank_id IS NOT NULL THEN 1 ELSE 0 END
     + CASE WHEN p.cid IS NOT NULL THEN 1 ELSE 0 END
     + 1)                                             AS source_count,
    d.mechanism_of_action,
    c.max_phase::INT                                   AS max_phase

FROM mol_bronze.chembl_molecules c
LEFT JOIN mol_bronze.drugbank d
       ON LOWER(d.inchi_key) = LOWER(c.inchi_key)
LEFT JOIN mol_bronze.pubchem p
       ON LOWER(p.inchi_key) = LOWER(c.inchi_key)
WHERE c.inchi_key IS NOT NULL
  AND c.pref_name IS NOT NULL
