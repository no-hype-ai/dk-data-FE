-- SQLMesh Model: Silver PubChem
-- Promotes mol_bronze.pubchem into mol_silver.pubchem with molecule-level linkage.
-- molecule_id is NULL — entity linking fills it by matching inchi_key against mol_silver.molecules.
-- Exposes PubChem compound data (CID, structure, physicochemical properties) to xenon sections:
--   molecule_profile, mechanism_of_action

MODEL (
    name mol_silver.pubchem,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (cid)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (cid, inchi_key))
    ),
    grain (cid)
);

SELECT
    gen_random_uuid()                       AS pubchem_id,
    NULL::UUID                              AS molecule_id,     -- entity linking fills this via inchi_key match
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

    -- Pharmacological / biological annotations
    b.pharmacological_actions,
    b.synonyms,
    b.mesh_headings,

    -- Cross-references
    b.cas_number,
    b.drugbank_ids,
    b.chembl_ids,
    b.unii,

    -- Source tracking
    'pubchem'                               AS source,
    b.created_at

FROM mol_bronze.pubchem b
WHERE b.processed_to_silver = FALSE
  AND b.cid IS NOT NULL
  AND b.inchi_key IS NOT NULL;
