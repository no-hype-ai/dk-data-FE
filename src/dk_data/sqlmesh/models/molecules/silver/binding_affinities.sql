-- SQLMesh Model: Silver Binding Affinities
-- Promotes mol_bronze.bindingdb into mol_silver.binding_affinities with molecule_id linkage.
--
-- Entity linking strategy (priority order):
--   1. InChIKey → mol_silver.molecules.inchi_key (most structurally precise)
--   2. ChEMBL ID → mol_silver.pubchem (via identifier_mappings in mol_silver.pubchem)
--   3. PubChem CID → mol_silver.pubchem.cid
--
-- Provides drug-target binding affinity data (Ki, IC50, Kd, EC50) linking
-- molecules to protein targets (UniProt ID) for mol_gold.molecule_profile
-- and competitive landscape models.

MODEL (
    name mol_silver.binding_affinities,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key bindingdb_id
    ),
    cron '@monthly',
    audits (
        not_null(columns := (bindingdb_id, activity_value_nm))
    ),
    grain bindingdb_id
);

SELECT
    gen_random_uuid()                                           AS id,

    -- Entity linkage: first matching strategy wins
    COALESCE(
        m_ik.molecule_id,
        pc_chembl.molecule_id,
        pc_cid.molecule_id
    )                                                           AS molecule_id,

    b.bindingdb_id,

    -- Ligand identifiers (for traceability / downstream joins)
    b.inchi_key,
    b.smiles,
    b.pubchem_cid,
    b.chembl_id,

    -- Target information
    b.target_name,
    b.target_organism,
    b.uniprot_id,

    -- Individual affinity measurements (all in nanomolar)
    b.ki_nm,
    b.ic50_nm,
    b.kd_nm,
    b.ec50_nm,

    -- Kinetics
    b.kon,
    b.koff,

    -- Best available activity value with type label
    b.activity_type,
    b.activity_value                                            AS activity_value_nm,
    b.activity_unit,

    -- Assay conditions
    b.assay_ph,
    b.assay_temp_c,

    -- Source literature
    b.pmid,
    b.doi,
    b.data_source,
    b.pdb_ids,

    'bindingdb'                                                 AS source,
    b.ingested_at                                               AS created_at

FROM mol_bronze.bindingdb b

-- Strategy 1: InChIKey (most precise structural match)
LEFT JOIN mol_silver.molecules m_ik
       ON b.inchi_key IS NOT NULL
      AND LOWER(m_ik.inchi_key) = LOWER(b.inchi_key)

-- Strategy 2: ChEMBL ID via identifier_mappings
--   mol_silver.pubchem stores chembl_ids as [{id, type}] objects, not a plain
--   string array, so @> to_jsonb(chembl_id) never matches.
--   Use identifier_mappings instead — reliable flat lookup.
LEFT JOIN mol_silver.identifier_mappings pc_chembl
       ON m_ik.molecule_id IS NULL
      AND b.chembl_id IS NOT NULL
      AND pc_chembl.identifier_type = 'chembl_id'
      AND pc_chembl.identifier_value = b.chembl_id

-- Strategy 3: PubChem CID via mol_silver.pubchem
LEFT JOIN mol_silver.pubchem pc_cid
       ON m_ik.molecule_id IS NULL
      AND pc_chembl.molecule_id IS NULL
      AND b.pubchem_cid IS NOT NULL
      AND pc_cid.cid = b.pubchem_cid::BIGINT

WHERE b.bindingdb_id IS NOT NULL
  AND b.activity_value IS NOT NULL;
