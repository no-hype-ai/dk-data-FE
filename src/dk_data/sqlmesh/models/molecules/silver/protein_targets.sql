-- SQLMesh Model: Silver Protein Targets
-- Combines mol_bronze.pdb_structures with mol_silver.targets (UniProt-derived)
-- to create a unified protein target record with structural context.
-- Used by: assessment pipeline via PostgREST (path: /protein_targets, schema: mol_silver).

MODEL (
    name mol_silver.protein_targets,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (target_id, source))
    )
);

-- PDB structures: link to target via uniprot_id, then to molecule via target
WITH pdb_linked AS (
    SELECT
        b.pdb_id                            AS structure_id,
        b.title,
        b.resolution,
        b.method,
        b.organism,
        b.ligand_id,
        b.ligand_name,
        b.uniprot_id,
        t.id                                AS target_id,
        t.protein_name,
        t.gene_name,
        t.target_type,
        t.molecule_id,
        'pdb'                               AS source,
        b.source_updated_at
    FROM mol_bronze.pdb_structures b
    LEFT JOIN mol_silver.targets t ON b.uniprot_id IS NOT NULL AND t.uniprot_id = b.uniprot_id
    WHERE b.pdb_id IS NOT NULL
)

SELECT
    gen_random_uuid()           AS id,
    molecule_id,
    target_id,
    protein_name,
    gene_name,
    target_type,
    uniprot_id,
    structure_id,
    title                       AS structure_title,
    resolution,
    method                      AS experimental_method,
    organism,
    ligand_id,
    ligand_name,
    source,
    source_updated_at,
    NOW()                       AS created_at
FROM pdb_linked;
