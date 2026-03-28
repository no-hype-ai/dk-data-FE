-- SQLMesh Model: Silver Protein Structures
-- PDB structural data linked to mol_silver.molecules via ligand ID → identifier_mappings
-- Feature: 019-cms-puf-platform-reconciliation — zero column loss audit
--
-- Purpose: PDB bronze was entirely unconsumed by silver. All bronze columns are
--   promoted here. molecule_id is resolved via the co-crystal ligand's PubChem CID
--   (through identifier_mappings). Structures with no drug ligand have molecule_id = NULL.
--
-- Column names match mol_bronze.pdb_structures exactly.

MODEL (
    name mol_silver.protein_structures,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key pdb_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (pdb_id)),
        unique_values(columns := (pdb_id))
    ),
    grain pdb_id
);

SELECT
    gen_random_uuid()               AS id,

    -- PDB identifiers (exact bronze column names from mol_bronze.pdb_structures)
    p.pdb_id,
    p.title,

    -- Experimental details
    p.method,
    p.resolution,
    p.molecular_weight,

    -- Dates
    p.deposit_date,
    p.release_date,

    -- Structural data
    p.polymer_entities,
    p.nonpolymer_entities,

    -- Primary ligand (co-crystal small molecule)
    p.ligand_id,
    p.ligand_name,

    -- Protein cross-reference
    p.uniprot_id,

    -- Organism
    p.source_organism,
    p.taxonomy_id,

    -- Molecule linkage via ligand → identifier_mappings (NULL when no match)
    im.molecule_id,

    -- Source tracking
    p.source,
    p.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.pdb_structures p
LEFT JOIN mol_silver.identifier_mappings im
    ON im.identifier_type = 'pdb_ligand'
    AND im.identifier_value = p.ligand_id
WHERE
    p.processed_to_silver = FALSE
    AND p.pdb_id IS NOT NULL;
