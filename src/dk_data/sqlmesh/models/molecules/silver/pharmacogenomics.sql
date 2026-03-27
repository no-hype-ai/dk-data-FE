-- SQLMesh Model: Silver Pharmacogenomics
-- Promotes mol_bronze.pharmgkb into mol_silver.pharmacogenomics with molecule_id linkage.
-- Entity linking: inchi_key → silver.molecules, then chembl_id, then drugbank_id fallback.
-- Provides PGx clinical annotations, dosing guidelines, variant annotations per molecule.

MODEL (
    name mol_silver.pharmacogenomics,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (pharmgkb_id))
    ),
    grain pharmgkb_id
);

SELECT
    gen_random_uuid()                                       AS id,
    COALESCE(m_ik.id, m_cid.id,
             m_db.id, m_name.id)                            AS molecule_id,
    b.pharmgkb_id,
    b.name,
    b.entity_type,
    b.drugbank_id,
    b.chembl_id,
    b.rxnorm_id,
    b.pubchem_cid,
    b.cas_number,
    b.drug_type,
    b.smiles,
    b.inchi_key,
    b.clinical_annotations,
    b.dosing_guidelines,
    b.drug_labels,
    b.variant_annotations,
    b.pathways,
    'pharmgkb'                                             AS source,
    b.source_updated_at,
    NOW()                                                  AS created_at

FROM mol_bronze.pharmgkb b
-- Link via inchi_key (most reliable)
LEFT JOIN silver.molecules m_ik
       ON b.inchi_key IS NOT NULL AND m_ik.inchi_key = b.inchi_key
-- Fallback: chembl_id via identifier_mappings
LEFT JOIN silver.identifier_mappings im_cid
       ON m_ik.id IS NULL
      AND b.chembl_id IS NOT NULL
      AND im_cid.identifier_type = 'chembl_id'
      AND im_cid.identifier_value = b.chembl_id
LEFT JOIN silver.molecules m_cid
       ON m_cid.id = im_cid.molecule_id
-- Fallback: drugbank_id via identifier_mappings
LEFT JOIN silver.identifier_mappings im_db
       ON m_ik.id IS NULL AND m_cid.id IS NULL
      AND b.drugbank_id IS NOT NULL
      AND im_db.identifier_type = 'drugbank_id'
      AND im_db.identifier_value = b.drugbank_id
LEFT JOIN silver.molecules m_db
       ON m_db.id = im_db.molecule_id
-- Fallback: name matching
LEFT JOIN silver.molecules m_name
       ON m_ik.id IS NULL AND m_cid.id IS NULL AND m_db.id IS NULL
      AND b.name IS NOT NULL
      AND LOWER(m_name.canonical_name) = LOWER(b.name)
WHERE b.pharmgkb_id IS NOT NULL;
