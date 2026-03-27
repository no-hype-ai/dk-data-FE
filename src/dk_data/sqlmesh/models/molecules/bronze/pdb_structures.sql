-- SQLMesh Model: Bronze PDB Protein Structures
-- Transforms raw PDB API responses (RCSB REST v1) to Bronze typed columns
-- Part of: 015-assessment-dashboard-integration
--
-- Source: mol_raw.pdb (envelope schema, migration 028)
-- RCSB JSON structure: rcsb_id, struct.title, exptl[].method,
--   rcsb_entry_info.resolution_combined[],
--   rcsb_accession_info.deposit_date,
--   rcsb_entry_info.molecular_weight,
--   polymer_entities[], nonpolymer_entities[]

MODEL (
    name mol_bronze.pdb_structures,
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

    -- Structure identifiers — rcsb_id is the 4-char PDB accession
    UPPER(COALESCE(
        response_body->>'rcsb_id',
        response_body->'entry'->>'id'
    )) AS pdb_id,

    response_body->'struct'->>'title' AS title,

    -- Experimental method (first entry in exptl array)
    response_body->'exptl'->0->>'method' AS method,

    -- Resolution in Angstroms (first value in resolution_combined array)
    (response_body->'rcsb_entry_info'->'resolution_combined'->0)::NUMERIC AS resolution,

    -- Molecular weight in Daltons
    (response_body->'rcsb_entry_info'->>'molecular_weight')::NUMERIC AS molecular_weight,

    -- Deposition and release dates
    (response_body->'rcsb_accession_info'->>'deposit_date')::DATE AS deposit_date,
    (response_body->'rcsb_accession_info'->>'initial_release_date')::DATE AS release_date,

    -- Polymer entities (protein chains, nucleic acids)
    response_body->'polymer_entities' AS polymer_entities,

    -- Non-polymer entities (ligands, small molecules)
    response_body->'nonpolymer_entities' AS nonpolymer_entities,

    -- First ligand (most common co-crystal case)
    response_body->'nonpolymer_entities'->0->'nonpolymer_comp'->>'comp_id' AS ligand_id,
    response_body->'nonpolymer_entities'->0->'nonpolymer_comp'->'chem_comp'->>'name' AS ligand_name,

    -- UniProt cross-reference from polymer entity (first chain, first UniProt ref)
    response_body->'polymer_entities'->0->'rcsb_polymer_entity_container_identifiers'->'uniprot_ids'->0 AS uniprot_id,

    -- Source organism
    response_body->'polymer_entities'->0->'rcsb_entity_source_organism'->0->>'scientific_name' AS source_organism,
    (response_body->'polymer_entities'->0->'rcsb_entity_source_organism'->0->>'ncbi_taxonomy_id')::INTEGER AS taxonomy_id,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'pdb' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.pdb
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND COALESCE(
        response_body->>'rcsb_id',
        response_body->'entry'->>'id'
    ) IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
