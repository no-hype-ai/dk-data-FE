-- SQLMesh Model: Silver PubChem
-- Promotes mol_bronze.pubchem into mol_silver.pubchem with molecule-level linkage.
-- Entity linking: LEFT JOIN mol_silver.molecules on inchi_key — most stable structural identifier.
-- FULL refresh ensures molecule_id is always current when new molecules are added.
-- Exposes PubChem compound data (CID, structure, physicochemical properties) to xenon sections:
--   molecule_profile, mechanism_of_action

MODEL (
    name mol_silver.pubchem,
    kind FULL,
    cron '@weekly',
    audits (
        not_null(columns := (cid, inchi_key))
    )
);

SELECT DISTINCT ON (b.cid)
    gen_random_uuid()                       AS pubchem_id,
    m.molecule_id,
    b.cid,
    b.inchi_key,

    -- Structure
    b.canonical_smiles,
    b.isomeric_smiles,
    b.iupac_name,
    b.inchi,
    b.molecular_formula,
    b.molecular_weight,
    b.exact_mass,

    -- Physicochemical properties
    b.xlogp,
    b.tpsa,
    b.complexity,
    b.charge,
    b.h_bond_donor_count,
    b.h_bond_acceptor_count,
    b.rotatable_bond_count,
    b.heavy_atom_count,
    b.atom_stereo_count,
    b.bond_stereo_count,
    b.covalent_unit_count,

    -- Pharmacological / biological annotations
    b.pharmacological_actions,
    b.synonyms,
    b.synonym_names,
    b.mesh_headings,

    -- Cross-references
    b.cas_number,
    b.drugbank_ids,
    b.chembl_ids,
    b.unii,
    b.taxonomy,
    b.patents,

    -- Bioassay data
    b.assay_ids,
    b.bioassay_count,

    -- Source tracking
    'pubchem'                               AS source,
    b.source_updated_at,
    b.request_timestamp                     AS ingested_at,
    b.created_at

FROM mol_bronze.pubchem b
LEFT JOIN mol_silver.molecules m ON LOWER(m.inchi_key) = LOWER(b.inchi_key)
WHERE b.cid IS NOT NULL
  AND b.inchi_key IS NOT NULL
ORDER BY b.cid, b.source_updated_at DESC NULLS LAST;
