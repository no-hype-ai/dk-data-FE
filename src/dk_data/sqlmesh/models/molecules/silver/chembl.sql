-- SQLMesh Model: Silver ChEMBL
-- Passthrough of mol_bronze.chembl with molecule_id linkage.
-- Exposes ChEMBL compound data (structures, properties, bioactivity metadata)
-- to the assessment pipeline via PostgREST (path: /chembl, schema: mol_silver).

MODEL (
    name mol_silver.chembl,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (chembl_id))
    ),
    grain chembl_id
);

SELECT
    gen_random_uuid()                   AS id,
    m.molecule_id,
    b.chembl_id,
    b.pref_name,
    b.molecule_type,
    b.max_phase,
    b.molecular_formula,
    b.molecular_weight,
    b.canonical_smiles,
    b.inchi,
    b.inchi_key,
    b.alogp,
    b.hba,
    b.hbd,
    b.psa,
    b.num_ro5_violations,
    b.aromatic_rings,
    b.heavy_atoms,
    b.first_approval,
    b.indication_class,
    b.usan_stem,
    b.therapeutic_flag,
    b.prodrug,
    b.natural_product,
    b.synonyms,
    b.cross_references,
    b.source,
    b.source_updated_at,
    NOW()                               AS created_at

FROM mol_bronze.chembl_molecules b
LEFT JOIN mol_silver.molecules m ON m.inchi_key = b.inchi_key
WHERE b.chembl_id IS NOT NULL;
