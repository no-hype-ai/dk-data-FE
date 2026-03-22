-- SQLMesh Model: Silver Targets
-- Zero data loss from Bronze. Column names match bronze (API-derived snake_case).
-- Entity linking: LEFT JOIN to mol_silver.molecules via ChEMBL cross-reference IDs.

MODEL (
    name mol_silver.targets,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key uniprot_id
    ),
    cron '@monthly',
    audits (
        not_null(columns := (uniprot_id, protein_name)),
        unique_values(columns := (uniprot_id))
    ),
    grain uniprot_id
);

SELECT
    gen_random_uuid() AS id,

    -- Entity linking: match via ChEMBL cross-reference
    m.molecule_id,

    -- All bronze columns with SAME NAMES as bronze model output
    b.uniprot_id,
    b.entry_name,
    b.entry_type,
    b.protein_name,
    b.short_name,
    b.alternative_names,
    b.submission_names,
    b.gene_name,
    b.genes,
    b.organism_scientific,
    b.organism_common,
    b.taxonomy_id,
    b.lineage,
    b.sequence,
    b.sequence_length,
    b.molecular_weight,
    b.sequence_checksum,
    b.comments,
    b.features,
    b.cross_references,
    b.secondary_accessions,
    b.keywords,
    b.go_terms,
    b.pdb_structures,
    b.annotation_score,
    b.extra_attributes,

    -- Derived: target type from keywords
    CASE
        WHEN b.keywords::TEXT ILIKE '%kinase%' THEN 'kinase'
        WHEN b.keywords::TEXT ILIKE '%receptor%' THEN 'receptor'
        WHEN b.keywords::TEXT ILIKE '%enzyme%' THEN 'enzyme'
        WHEN b.keywords::TEXT ILIKE '%transporter%' THEN 'transporter'
        WHEN b.keywords::TEXT ILIKE '%ion channel%' THEN 'ion_channel'
        WHEN b.keywords::TEXT ILIKE '%protease%' THEN 'protease'
        ELSE 'other'
    END AS target_type,

    -- Source tracking
    b.id AS bronze_id,
    b.created_at AS ingested_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.uniprot b
LEFT JOIN LATERAL (
    SELECT mol.molecule_id
    FROM mol_silver.molecules mol
    WHERE EXISTS (
        SELECT 1
        FROM jsonb_array_elements(COALESCE(b.cross_references, '[]'::jsonb)) AS ref
        WHERE ref->>'database' = 'ChEMBL'
          AND ref->>'id' = mol.chembl_id
    )
    ORDER BY mol.resolution_confidence DESC
    LIMIT 1
) m ON TRUE
WHERE
    b.processed_to_silver = FALSE
    AND b.uniprot_id IS NOT NULL
    AND b.protein_name IS NOT NULL;
