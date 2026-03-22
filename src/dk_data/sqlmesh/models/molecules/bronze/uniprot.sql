-- SQLMesh Model: Bronze UniProt
-- Transforms Raw UniProt protein responses to Bronze typed columns
-- Part of: 012-dk-data-platform

MODEL (
    name mol_bronze.uniprot,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@daily',
    audits (
        not_null(columns := (uniprot_id)),
        unique_values(columns := (uniprot_id))
    ),
    grain uniprot_id
);

-- Unnest paginated API responses: UniProt returns {"results": [...]} bulk lists
-- or single-protein objects at root. Both shapes are handled.
WITH expanded AS (
    SELECT
        raw.id              AS raw_source_id,
        raw.request_timestamp,
        protein.value       AS p
    FROM mol_raw.uniprot AS raw,
    LATERAL jsonb_array_elements(
        CASE
            WHEN raw.response_body ? 'results' THEN raw.response_body->'results'
            WHEN raw.response_body ? 'primaryAccession' THEN jsonb_build_array(raw.response_body)
            ELSE '[]'::jsonb
        END
    ) AS protein(value)
    WHERE raw.response_status = 200
      AND raw.processed_to_bronze = FALSE
      AND raw.request_timestamp BETWEEN @start_dt AND @end_dt
),
deduped AS (
    SELECT DISTINCT ON (p->>'primaryAccession')
        raw_source_id, request_timestamp, p
    FROM expanded
    WHERE p->>'primaryAccession' IS NOT NULL
    ORDER BY p->>'primaryAccession', request_timestamp DESC
)

SELECT
    gen_random_uuid() AS id,

    -- UniProt Identifiers (names from actual API response)
    p->>'primaryAccession' AS uniprot_id,
    p->>'uniProtkbId' AS entry_name,
    p->>'entryType' AS entry_type,

    -- Protein Names
    p->'proteinDescription'->'recommendedName'->>'fullName' AS protein_name,
    p->'proteinDescription'->'recommendedName'->>'shortName' AS short_name,
    p->'proteinDescription'->'alternativeNames' AS alternative_names,
    p->'proteinDescription'->'submissionNames' AS submission_names,

    -- Gene Names
    (p->'genes'->0->'geneName'->>'value') AS gene_name,
    p->'genes' AS genes,

    -- Organism
    p->'organism'->>'scientificName' AS organism_scientific,
    p->'organism'->>'commonName' AS organism_common,
    (p->'organism'->>'taxonId')::INTEGER AS taxonomy_id,
    p->'organism'->'lineage' AS lineage,

    -- Sequence
    p->'sequence'->>'value' AS sequence,
    (p->'sequence'->>'length')::INTEGER AS sequence_length,
    (p->'sequence'->>'molWeight')::INTEGER AS molecular_weight,
    p->'sequence'->>'checksum' AS sequence_checksum,

    -- Function
    p->'comments' AS comments,

    -- Features (domains, binding sites, etc.)
    p->'features' AS features,

    -- Cross-references
    p->'uniProtKBCrossReferences' AS cross_references,
    p->'secondaryAccessions' AS secondary_accessions,

    -- Keywords
    p->'keywords' AS keywords,

    -- GO Terms
    (SELECT jsonb_agg(ref)
     FROM jsonb_array_elements(COALESCE(p->'uniProtKBCrossReferences', '[]'::jsonb)) AS ref
     WHERE ref->>'database' = 'GO') AS go_terms,

    -- PDB structures
    (SELECT jsonb_agg(ref)
     FROM jsonb_array_elements(COALESCE(p->'uniProtKBCrossReferences', '[]'::jsonb)) AS ref
     WHERE ref->>'database' = 'PDB') AS pdb_structures,

    -- Evidence and Annotation
    p->>'annotationScore' AS annotation_score,
    p->'extraAttributes' AS extra_attributes,

    -- Raw source tracking
    p AS raw_json,
    raw_source_id,
    'uniprot' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM deduped;
