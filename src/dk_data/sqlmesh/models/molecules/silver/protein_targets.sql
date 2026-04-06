-- SQLMesh Model: Silver Protein Targets
-- Combines mol_bronze.pdb_structures with mol_silver.targets (UniProt-derived)
-- to create a unified protein target record with structural context.
-- Used by: assessment pipeline via PostgREST (path: /protein_targets, schema: mol_silver).

MODEL (
    name mol_silver.protein_targets,
    kind FULL,
    cron '@daily',
    audits (
        -- target_id may be NULL for PDB structures whose UniProt ID is not yet in mol_silver.targets.
        -- Audit on source only to ensure every row has a provenance label.
        not_null(columns := (source))
    )
);

-- PDB structures: link to target via uniprot_id, then to molecule via target
WITH pdb_linked AS (
    SELECT
        b.pdb_id                            AS structure_id,
        b.title,
        b.resolution,
        b.method,
        b.molecular_weight,
        b.deposit_date,
        b.release_date,
        b.polymer_entities,
        b.nonpolymer_entities,
        b.source_organism AS organism,
        b.taxonomy_id,
        b.ligand_id,
        b.ligand_name,
        b.uniprot_id,
        t.id                                AS target_id,
        t.target_name                       AS protein_name,
        t.gene_symbol                       AS gene_name,
        t.target_type,
        mt.molecule_id                      AS molecule_id,
        'pdb'                               AS source,
        b.source_updated_at
    FROM mol_bronze.pdb_structures b
    LEFT JOIN mol_silver.targets t ON b.uniprot_id IS NOT NULL
        AND t.uniprot_id = ANY(
            ARRAY(SELECT jsonb_array_elements_text(
                CASE jsonb_typeof(b.uniprot_id)
                    WHEN 'array' THEN b.uniprot_id
                    ELSE jsonb_build_array(b.uniprot_id)
                END
            ))
        )
    LEFT JOIN (
        SELECT DISTINCT ON (target_id) target_id, molecule_id
        FROM mol_silver.molecule_targets
        ORDER BY target_id, molecule_id
    ) mt ON mt.target_id = t.id
    WHERE b.pdb_id IS NOT NULL
)

-- DISTINCT ON (structure_id): a PDB structure can have multiple UniProt IDs (JSONB array);
-- each maps to a different target row after the lateral JOIN, producing one row per
-- (structure_id, target_id) pair. We keep only the first target per structure to preserve
-- the 1:1 structure→row grain expected by downstream consumers.
SELECT DISTINCT ON (structure_id)
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
    molecular_weight,
    deposit_date,
    release_date,
    polymer_entities,
    nonpolymer_entities,
    organism,
    taxonomy_id,
    ligand_id,
    ligand_name,
    source,
    source_updated_at,
    NOW()                       AS created_at
FROM pdb_linked
ORDER BY structure_id, target_id NULLS LAST;
