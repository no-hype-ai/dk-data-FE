-- SQLMesh Model: Silver Targets
-- Zero data loss from Bronze. Column names match bronze (API-derived snake_case).
-- Adds: molecule_id linkage via chembl_ids.

MODEL (
    name mol_silver.targets,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key primaryaccession
    ),
    cron '@monthly',
    audits (
        not_null(columns := (primaryaccession, protein_name)),
        unique_values(columns := (primaryaccession))
    ),
    grain primaryaccession
);

SELECT
    gen_random_uuid() AS id,
    m.molecule_id,

    -- All bronze columns with SAME NAMES (no renames)
    b.accession,
    b.annotationscore,
    b.chembl_ids,
    b.comments,
    b.drugbank_ids,
    b.entry_name,
    b.entrytype,
    b.features,
    b.function_description,
    b.gene_names,
    b.genes,
    b.keywords,
    b.organism,
    b.organism_commonname,
    b.organism_id,
    b.organism_lineage,
    b.organism_scientificname,
    b.organism_taxonid,
    b.pdb_ids,
    b.primaryaccession,
    b.protein_name,
    b.proteindescription_alternativenames,
    b.proteindescription_recommendedname_fullname,
    b.proteindescription_recommendedname_shortnames,
    b.proteinexistence,
    b.references,
    b.secondaryaccessions,
    b.sequence,
    b.sequence_crc64,
    b.sequence_length,
    b.sequence_mass,
    b.sequence_md5,
    b.sequence_molweight,
    b.sequence_value,
    b.subcellular_location,
    b.tissue_specificity,
    b.uniprotkbcrossreferences,
    b.uniprotkbid,

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
    b.ingested_at,
    NOW() AS created_at,
    NOW() AS updated_at

FROM mol_bronze.uniprot b
LEFT JOIN mol_silver.molecules m ON (
    m.chembl_id = ANY(
        ARRAY(SELECT jsonb_array_elements_text(b.chembl_ids))
    )
)
WHERE
    b.processed_to_silver = FALSE
    AND b.primaryaccession IS NOT NULL
    AND b.protein_name IS NOT NULL;
