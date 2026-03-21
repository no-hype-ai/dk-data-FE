-- SQLMesh Model: Bronze PDB Protein Structures
-- Transforms raw PDB API responses to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration

MODEL (
    name bronze.pdb_structures,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (pdb_id)),
        unique_values(columns := (pdb_id))
    ),
    grain pdb_id
);

SELECT
    gen_random_uuid() AS id,

    -- Structure identifiers
    response_body->>'structureId' AS pdb_id,
    response_body->>'title' AS title,
    (response_body->>'resolution')::NUMERIC AS resolution,
    response_body->>'experimentalTechnique' AS method,
    response_body->>'source' AS organism,

    -- Ligand info
    response_body->'ligands'->0->>'chemicalID' AS ligand_id,
    response_body->'ligands'->0->>'chemicalName' AS ligand_name,

    -- Cross-references
    response_body->>'uniprotId' AS uniprot_id,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'pdb_structures' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.pdb_structures
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'structureId' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
