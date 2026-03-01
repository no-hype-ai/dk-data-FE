-- SQLMesh Model: Silver Targets
-- Normalized molecular target data from UniProt and ChEMBL
-- Part of: 012-dk-data-platform

MODEL (
    name silver.targets,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key uniprot_id
    ),
    cron '@monthly',
    audits (
        not_null(columns := (uniprot_id, target_name)),
        unique_values(columns := (uniprot_id))
    ),
    grain uniprot_id
);

WITH uniprot_targets AS (
    SELECT
        uniprot_id,
        protein_name AS target_name,
        short_name,
        gene_name,
        entry_name,
        entry_type,
        organism_scientific,
        organism_common,
        taxonomy_id,
        sequence,
        sequence_length,
        molecular_weight,
        go_terms,
        pdb_structures,
        keywords,
        -- Determine target type from entry type and keywords
        CASE
            WHEN keywords::TEXT ILIKE '%kinase%' THEN 'kinase'
            WHEN keywords::TEXT ILIKE '%receptor%' THEN 'receptor'
            WHEN keywords::TEXT ILIKE '%enzyme%' THEN 'enzyme'
            WHEN keywords::TEXT ILIKE '%transporter%' THEN 'transporter'
            WHEN keywords::TEXT ILIKE '%ion channel%' THEN 'ion_channel'
            WHEN keywords::TEXT ILIKE '%protease%' THEN 'protease'
            ELSE 'other'
        END AS target_type,
        source,
        source_updated_at,
        created_at
    FROM bronze.uniprot
    WHERE
        processed_to_silver = FALSE
        AND uniprot_id IS NOT NULL
        AND protein_name IS NOT NULL
)

SELECT
    gen_random_uuid() AS id,
    uniprot_id,
    target_name,
    short_name AS target_short_name,
    gene_name AS gene_symbol,
    entry_name,
    target_type,
    organism_scientific AS organism,
    organism_common,
    taxonomy_id,
    sequence_length,
    molecular_weight,
    -- Extract GO terms as separate fields
    (SELECT jsonb_agg(g->>'id')
     FROM jsonb_array_elements(go_terms) AS g
     WHERE g->>'id' LIKE 'GO:0008150%') AS go_biological_process,
    (SELECT jsonb_agg(g->>'id')
     FROM jsonb_array_elements(go_terms) AS g
     WHERE g->>'id' LIKE 'GO:0005575%') AS go_cellular_component,
    (SELECT jsonb_agg(g->>'id')
     FROM jsonb_array_elements(go_terms) AS g
     WHERE g->>'id' LIKE 'GO:0003674%') AS go_molecular_function,
    -- PDB count
    COALESCE(jsonb_array_length(pdb_structures), 0) AS pdb_structure_count,
    pdb_structures,
    keywords,
    NULL::TEXT AS chembl_target_id,  -- To be linked if available
    source,
    source_updated_at,
    NOW() AS created_at,
    NOW() AS updated_at
FROM uniprot_targets;


-- NOTE: Bronze processed_to_silver flag updates are handled outside SQLMesh.
-- Silver models use INCREMENTAL_BY_UNIQUE_KEY with INCREMENTAL_BY_UNIQUE_KEY (default: update all columns on match),
-- so reprocessing is idempotent.

-- =========================================================================
-- Feature 015: PDB structural data enrichment
-- PDB structures are joined to existing UniProt targets via uniprot_id.
-- This enrichment adds experimental structure data (resolution, method)
-- to target records that have PDB cross-references.
--
-- Integration note: PDB data enriches existing target records rather than
-- adding new rows. The bronze.pdb_structures model provides pdb_id,
-- resolution, method, ligand_id, ligand_name mapped via uniprot_id.
-- A future iteration should LEFT JOIN pdb data into the main target query
-- to populate pdb_structure_count with actual experimental counts.
-- =========================================================================
