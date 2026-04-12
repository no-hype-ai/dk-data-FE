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
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (pdb_id)),
        unique_values(columns := (pdb_id))
    ),
    grain pdb_id
);

-- Deduplicate bronze first: PDB structures may be ingested multiple times
-- (same pdb_id from overlapping API calls). DISTINCT ON keeps the most recent.
WITH deduped_pdb AS (
    SELECT DISTINCT ON (pdb_id)
        pdb_id, title, method, resolution, molecular_weight,
        deposit_date, release_date, polymer_entities, nonpolymer_entities,
        ligand_id, ligand_name, uniprot_id, source_organism, taxonomy_id,
        source, source_updated_at
    FROM mol_bronze.pdb_structures
    WHERE pdb_id IS NOT NULL
    ORDER BY pdb_id, source_updated_at DESC NULLS LAST
)

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
    -- Use subquery to avoid fan-out when multiple molecules map to the same ligand.
    (
        SELECT im.molecule_id
        FROM mol_silver.molecule_identifiers im
        WHERE im.source = 'pubchem'
          AND im.identifier = p.ligand_id
        ORDER BY im.confidence DESC NULLS LAST
        LIMIT 1
    )                               AS molecule_id,

    -- Source tracking
    p.source,
    p.source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM deduped_pdb p;
