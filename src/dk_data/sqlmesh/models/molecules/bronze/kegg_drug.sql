-- SQLMesh Model: Bronze KEGG Drug
-- Transforms raw KEGG Drug API responses into typed bronze layer.
-- Response: {"entries": [{entry, name, formula, smiles, targets, pathways, ...}]}
--        or a single entry at top level.
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.kegg_drug,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@weekly',
    grain kegg_id,
    audits (
        not_null(columns := (kegg_id))
    )
);

WITH unnested AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        entry
    FROM mol_raw.kegg_drug r,
         jsonb_array_elements(
             CASE
                 WHEN r.response_body->'entries' IS NOT NULL AND jsonb_typeof(r.response_body->'entries') = 'array'
                     THEN r.response_body->'entries'
                 ELSE jsonb_build_array(r.response_body)
             END
         ) AS entry
    WHERE r.response_status = 200
      AND r.response_body IS NOT NULL
)

SELECT DISTINCT ON (kegg_id)
    gen_random_uuid()   AS id,
    raw_id,

    COALESCE(
        entry->>'entry',
        entry->>'kegg_id',
        entry->>'id'
    ) AS kegg_id,
    entry->>'name'      AS name,
    entry->>'formula'   AS formula,
    (entry->>'exact_mass')::NUMERIC AS exact_mass,
    entry->>'smiles'    AS smiles,
    entry->>'inchi'     AS inchi,
    COALESCE(entry->>'inchi_key', entry->>'inchikey') AS inchi_key,

    entry->'drug_class' AS drug_class,
    entry->'atc_codes'  AS atc_codes,
    COALESCE(entry->>'target', entry->>'therapeutic_target') AS therapeutic_target,
    entry->'targets'    AS targets,
    entry->'pathways'   AS pathways,
    entry->'enzymes'    AS enzymes,

    entry->>'drugbank_id' AS drugbank_id,
    (entry->>'pubchem_sid')::BIGINT AS pubchem_sid,
    entry->>'chembl_id'   AS chembl_id,
    entry->>'cas_number'  AS cas_number,
    entry->'research_codes' AS research_codes,
    entry->'synonyms'     AS synonyms,

    FALSE               AS processed_to_silver,
    request_timestamp,
    request_timestamp   AS ingested_at,
    'kegg_drug'         AS source,
    request_timestamp   AS source_updated_at

FROM unnested
WHERE COALESCE(entry->>'entry', entry->>'kegg_id', entry->>'id') IS NOT NULL
ORDER BY kegg_id, request_timestamp DESC NULLS LAST
