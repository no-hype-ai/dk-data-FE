-- SQLMesh Model: Silver Pathways
-- Combines Reactome biological pathways and KEGG drug pathway annotations
-- into a unified mol_silver.pathways table with molecule_id linkage.
-- Used by: assessment pipeline via PostgREST (path: /pathways, schema: mol_silver).

MODEL (
    name mol_silver.pathways,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (pathway_id, source)
    ),
    cron '@monthly',
    grain (pathway_id, source),
    audits (
        not_null(columns := (pathway_id, pathway_name, source))
    )
);

-- Reactome pathways: linked to molecule via search query stored in request_params
WITH reactome_linked AS (
    SELECT
        b.stable_id                                     AS pathway_id,
        b.db_id,
        b.pathway_name,
        b.entity_type,
        b.species,
        b.relevance_score,
        b.class_name,
        b.source,
        b.source_updated_at,
        b.ingested_at,
        -- Molecule linkage: request_params carries the drug name that triggered the search
        COALESCE(m_name.molecule_id, m_alias.molecule_id) AS molecule_id
    FROM mol_bronze.reactome b
    LEFT JOIN mol_silver.molecules m_name
           ON b.raw_json->>'query' IS NOT NULL
          AND LOWER(m_name.canonical_name) = LOWER(b.raw_json->>'query')
    -- Deduplicated alias lookup — 375+ dup normalized_name rows exist
    LEFT JOIN (
        SELECT DISTINCT ON (normalized_name)
            normalized_name, molecule_id
        FROM mol_silver.molecule_names
        ORDER BY normalized_name, molecule_id
    ) ma ON m_name.molecule_id IS NULL
          AND b.raw_json->>'query' IS NOT NULL
          AND LOWER(REGEXP_REPLACE(b.raw_json->>'query', '[^a-zA-Z0-9]', '', 'g'))
              = ma.normalized_name
    LEFT JOIN mol_silver.molecules m_alias ON m_alias.molecule_id = ma.molecule_id
    WHERE b.stable_id IS NOT NULL
),

-- KEGG Drug pathways: each KEGG entry has a pathways JSONB array
kegg_pathways AS (
    SELECT
        kp.value->>'id'                                 AS pathway_id,
        NULL::BIGINT                                    AS db_id,
        kp.value->>'name'                               AS pathway_name,
        'pathway'                                       AS entity_type,
        'Homo sapiens'                                  AS species,
        NULL::NUMERIC                                   AS relevance_score,
        NULL::TEXT                                      AS class_name,
        'kegg'                                          AS source,
        b.source_updated_at,
        b.ingested_at,
        m.molecule_id
    FROM mol_bronze.kegg_drug b
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(b.pathways, '[]'::jsonb)) AS kp(value)
    LEFT JOIN mol_silver.molecules m ON b.inchi_key IS NOT NULL AND m.inchi_key = b.inchi_key
    WHERE kp.value->>'id' IS NOT NULL
)

SELECT
    gen_random_uuid()   AS id,
    molecule_id,
    pathway_id,
    db_id,
    pathway_name,
    entity_type,
    species,
    relevance_score,
    class_name,
    source,
    source_updated_at,
    ingested_at,
    NOW()               AS created_at
FROM reactome_linked

UNION ALL

SELECT
    gen_random_uuid()   AS id,
    molecule_id,
    pathway_id,
    db_id,
    pathway_name,
    entity_type,
    species,
    relevance_score,
    class_name,
    source,
    source_updated_at,
    ingested_at,
    NOW()               AS created_at
FROM kegg_pathways;
