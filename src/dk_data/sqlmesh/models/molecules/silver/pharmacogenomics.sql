-- SQLMesh Model: Silver Pharmacogenomics
-- Promotes mol_bronze.pharmgkb into mol_silver.pharmacogenomics with molecule_id linkage.
-- Entity linking: inchi_key → mol_silver.molecules, then chembl_id, then drugbank_id fallback.
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
    COALESCE(m_ik.molecule_id, m_cid.molecule_id,
             m_db.molecule_id, m_name.molecule_id)                            AS molecule_id,
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
    b.ingested_at,
    NOW()                                                  AS created_at

FROM mol_bronze.pharmgkb b
-- Link via inchi_key (most reliable; inchi_key is unique in molecules)
LEFT JOIN mol_silver.molecules m_ik
       ON b.inchi_key IS NOT NULL AND m_ik.inchi_key = b.inchi_key
-- Fallback: chembl_id via identifier_mappings — deduplicated (24 dups per chembl_id)
LEFT JOIN (
    SELECT DISTINCT ON (identifier_value)
        identifier_value, molecule_id
    FROM mol_silver.identifier_mappings
    WHERE identifier_type = 'chembl_id'
    ORDER BY identifier_value, molecule_id
) im_cid ON m_ik.molecule_id IS NULL
      AND b.chembl_id IS NOT NULL
      AND im_cid.identifier_value = b.chembl_id
LEFT JOIN mol_silver.molecules m_cid
       ON m_cid.molecule_id = im_cid.molecule_id
-- Fallback: drugbank_id via identifier_mappings — deduplicated (24 dups per drugbank_id)
LEFT JOIN (
    SELECT DISTINCT ON (identifier_value)
        identifier_value, molecule_id
    FROM mol_silver.identifier_mappings
    WHERE identifier_type = 'drugbank_id'
    ORDER BY identifier_value, molecule_id
) im_db ON m_ik.molecule_id IS NULL AND m_cid.molecule_id IS NULL
      AND b.drugbank_id IS NOT NULL
      AND im_db.identifier_value = b.drugbank_id
LEFT JOIN mol_silver.molecules m_db
       ON m_db.molecule_id = im_db.molecule_id
-- Fallback: name matching
LEFT JOIN mol_silver.molecules m_name
       ON m_ik.molecule_id IS NULL AND m_cid.molecule_id IS NULL AND m_db.molecule_id IS NULL
      AND b.name IS NOT NULL
      AND LOWER(m_name.canonical_name) = LOWER(b.name)
WHERE b.pharmgkb_id IS NOT NULL;
