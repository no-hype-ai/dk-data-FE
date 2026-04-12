-- SQLMesh Model: Bronze KEGG Drug
-- Transforms raw KEGG Drug API responses into typed bronze layer.
-- Response: {"entries": [{entry, name, formula, smiles, targets, pathways, ...}]}
--        or a single entry at top level.
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.kegg_drug,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key kegg_id
    ),
    cron '@weekly',
    grain kegg_id,
    audits (
        not_null(columns := (kegg_id)),
        unique_values(columns := (kegg_id))
    ),
    pre_statements [
        SET LOCAL work_mem = '128MB'
    ]
);

WITH unnested AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        entry,
        entry AS raw_json
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
      AND r.processed_to_bronze = FALSE
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
    -- KEGG flat-file STDINCHI/STDINCHIKEY are parsed as arrays by the fetcher
    COALESCE(entry->'stdinchi'->>0, entry->>'inchi')                          AS inchi,
    COALESCE(entry->'stdinchikey'->>0, entry->>'inchi_key', entry->>'inchikey') AS inchi_key,

    entry->'drug_class' AS drug_class,
    entry->'atc_codes'  AS atc_codes,
    COALESCE(entry->>'target', entry->>'therapeutic_target') AS therapeutic_target,
    entry->'targets'    AS targets,
    -- KEGG flat-file PATHWAY is parsed as list under key "pathway" (singular) by the fetcher
    COALESCE(entry->'pathway', entry->'pathways')   AS pathways,
    entry->'enzymes'    AS enzymes,

    -- KEGG flat-file DBLINKS is parsed as a JSON array of "Key: Value" strings.
    -- e.g. dblinks = ["CAS: 65-49-6", "DrugBank: DB00551", "PubChem: 4", "ChEMBL: CHEMBL416"]
    -- Use #>> '{}' to extract text from JSONB string elements without surrounding quotes.
    (SELECT regexp_replace(elem #>> '{}', '^DrugBank: ', '')
     FROM jsonb_array_elements(entry->'dblinks') AS elem
     WHERE (elem #>> '{}') LIKE 'DrugBank: %'
     LIMIT 1
    ) AS drugbank_id,
    (SELECT (regexp_replace(elem #>> '{}', '^PubChem: ', ''))::BIGINT
     FROM jsonb_array_elements(entry->'dblinks') AS elem
     WHERE (elem #>> '{}') LIKE 'PubChem: %'
     LIMIT 1
    ) AS pubchem_sid,
    (SELECT regexp_replace(elem #>> '{}', '^ChEMBL: ', '')
     FROM jsonb_array_elements(entry->'dblinks') AS elem
     WHERE (elem #>> '{}') LIKE 'ChEMBL: %'
     LIMIT 1
    ) AS chembl_id,
    (SELECT regexp_replace(elem #>> '{}', '^CAS: ', '')
     FROM jsonb_array_elements(entry->'dblinks') AS elem
     WHERE (elem #>> '{}') LIKE 'CAS: %'
     LIMIT 1
    ) AS cas_number,
    entry->'research_codes' AS research_codes,
    entry->'synonyms'     AS synonyms,

    raw_json,
    FALSE               AS processed_to_silver,
    request_timestamp,
    request_timestamp   AS ingested_at,
    'kegg_drug'         AS source,
    request_timestamp   AS source_updated_at

FROM unnested
WHERE COALESCE(entry->>'entry', entry->>'kegg_id', entry->>'id') IS NOT NULL
ORDER BY kegg_id, request_timestamp DESC NULLS LAST
