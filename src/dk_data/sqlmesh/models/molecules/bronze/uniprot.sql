-- SQLMesh Model: Bronze UniProt
-- Transforms Raw UniProt protein responses to Bronze typed columns
-- Part of: 012-dk-data-platform

MODEL (
    name mol_bronze.uniprot,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key uniprot_id
    ),
    cron '@monthly',
    audits (
        not_null(columns := (uniprot_id)),
        unique_values(columns := (uniprot_id))
    ),
    grain uniprot_id
);

SELECT
    gen_random_uuid() AS id,

    -- UniProt Identifiers
    response_body->>'primaryAccession' AS uniprot_id,
    response_body->>'uniProtkbId' AS entry_name,
    response_body->>'entryType' AS entry_type,

    -- Protein Names
    -- fullName is an object: {"evidences": [...], "value": "..."}
    response_body->'proteinDescription'->'recommendedName'->'fullName'->>'value' AS protein_name,
    -- shortNames is an array of {value, evidences} objects
    response_body->'proteinDescription'->'recommendedName'->'shortNames'->0->>'value' AS short_name,
    response_body->'proteinDescription'->'alternativeNames' AS alternative_names,
    response_body->'proteinDescription'->'submissionNames' AS submission_names,

    -- Gene Names
    (response_body->'genes'->0->'geneName'->>'value') AS gene_name,
    response_body->'genes' AS genes,

    -- Organism
    response_body->'organism'->>'scientificName' AS organism_scientific,
    response_body->'organism'->>'commonName' AS organism_common,
    (response_body->'organism'->>'taxonId')::INTEGER AS taxonomy_id,
    response_body->'organism'->'lineage' AS lineage,

    -- Sequence
    response_body->'sequence'->>'value' AS sequence,
    (response_body->'sequence'->>'length')::INTEGER AS sequence_length,
    (response_body->'sequence'->>'molWeight')::INTEGER AS molecular_weight,
    response_body->'sequence'->>'checksum' AS sequence_checksum,

    -- Function
    response_body->'comments' AS comments,

    -- Features (domains, binding sites, etc.)
    response_body->'features' AS features,

    -- Cross-references
    response_body->'uniProtKBCrossReferences' AS cross_references,
    response_body->'secondaryAccessions' AS secondary_accessions,

    -- Keywords
    response_body->'keywords' AS keywords,

    -- GO Terms (all GO cross-references; ontology determined by GoTerm property prefix)
    -- P: = Biological Process, C: = Cellular Component, F: = Molecular Function
    (SELECT jsonb_agg(ref)
     FROM jsonb_array_elements(response_body->'uniProtKBCrossReferences') AS ref
     WHERE ref->>'database' = 'GO') AS go_terms,

    -- PDB structures (cross-references to RCSB PDB)
    (SELECT jsonb_agg(ref)
     FROM jsonb_array_elements(response_body->'uniProtKBCrossReferences') AS ref
     WHERE ref->>'database' = 'PDB') AS pdb_structures,

    -- Evidence and Annotation (float 0.0–5.0)
    (response_body->>'annotationScore')::NUMERIC AS annotation_score,
    response_body->'extraAttributes' AS extra_attributes,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'uniprot' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.uniprot
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'primaryAccession' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
