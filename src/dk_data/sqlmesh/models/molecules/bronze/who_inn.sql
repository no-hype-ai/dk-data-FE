-- SQLMesh Model: Bronze WHO INN
-- Transforms raw WHO International Nonproprietary Names API responses into typed bronze layer.
-- Handles both direct INN entries and PubChem synonyms format (used for INN lookup).
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.who_inn,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 500
    ),
    cron '@weekly',
    grain inn_name,
    audits (
        not_null(columns := (inn_name))
    )
);

-- Direct INN entry format: response_body has inn_name, cas_number, inn_stem, research_codes, etc.
WITH direct_entries AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,

        COALESCE(
            r.response_body->>'inn_name',
            r.response_body->>'name'
        ) AS inn_name,
        r.response_body->>'inn_latin'                         AS inn_latin,
        (r.response_body->>'list_number')::INTEGER            AS inn_list_number,
        (r.response_body->>'year')::INTEGER                   AS inn_year,
        r.response_body->>'cas_number'                        AS cas_number,
        r.response_body->>'molecular_formula'                 AS molecular_formula,
        r.response_body->>'smiles'                            AS smiles,
        COALESCE(
            r.response_body->>'inchi_key',
            r.response_body->>'inchikey'
        ) AS inchi_key,
        r.response_body->>'stem'                              AS inn_stem,
        r.response_body->>'stem_definition'                   AS stem_definition,
        r.response_body->'research_codes'                     AS research_codes,
        r.response_body->'synonyms'                           AS synonyms,
        COALESCE(r.response_body->>'status', 'published')     AS status,
        r.request_timestamp                                   AS source_updated_at

    FROM mol_raw.who_inn r
    WHERE r.response_status = 200
      AND r.response_body IS NOT NULL
      -- Direct format: has inn_name or name at top level
      AND (r.response_body->>'inn_name' IS NOT NULL
           OR r.response_body->>'name' IS NOT NULL)
      -- Exclude PubChem synonyms format (handled below)
      AND r.response_body->'InformationList' IS NULL
),

-- PubChem synonyms format: response_body->InformationList->Information[]->{Synonym:[...]}
-- INN is typically the lowercase synonym; research codes are alphanumeric with hyphens
pubchem_synonyms AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        info_item,
        r.request_timestamp AS source_updated_at

    FROM mol_raw.who_inn r,
         jsonb_array_elements(r.response_body->'InformationList'->'Information') AS info_item
    WHERE r.response_status = 200
      AND r.response_body->'InformationList' IS NOT NULL
),

pubchem_extracted AS (
    SELECT
        raw_id,
        request_timestamp,
        -- INN name: first lowercase synonym (INN names are lowercase by convention)
        (SELECT s
         FROM jsonb_array_elements_text(info_item->'Synonym') AS s
         WHERE s = lower(s) AND s !~ '[0-9]'
         LIMIT 1
        ) AS inn_name,
        -- Research codes: uppercase with digits and hyphens (e.g. CP-690,550)
        (SELECT jsonb_agg(s)
         FROM jsonb_array_elements_text(info_item->'Synonym') AS s
         WHERE s ~ '^[A-Z][A-Z0-9]+-[0-9]'
         LIMIT 10
        ) AS research_codes,
        (SELECT jsonb_agg(s)
         FROM jsonb_array_elements_text(info_item->'Synonym') AS s
         LIMIT 20
        ) AS synonyms,
        source_updated_at
    FROM pubchem_synonyms
),

combined AS (
    SELECT
        raw_id,
        request_timestamp,
        inn_name,
        NULL::TEXT AS inn_latin,
        NULL::INTEGER AS inn_list_number,
        NULL::INTEGER AS inn_year,
        NULL::TEXT AS cas_number,
        NULL::TEXT AS molecular_formula,
        NULL::TEXT AS smiles,
        NULL::TEXT AS inchi_key,
        NULL::TEXT AS inn_stem,
        NULL::TEXT AS stem_definition,
        research_codes,
        synonyms,
        'published' AS status,
        source_updated_at
    FROM pubchem_extracted
    WHERE inn_name IS NOT NULL

    UNION ALL

    SELECT
        raw_id,
        request_timestamp,
        inn_name,
        inn_latin,
        inn_list_number,
        inn_year,
        cas_number,
        molecular_formula,
        smiles,
        inchi_key,
        inn_stem,
        stem_definition,
        research_codes,
        synonyms,
        status,
        source_updated_at
    FROM direct_entries
    WHERE inn_name IS NOT NULL
)

SELECT DISTINCT ON (inn_name)
    gen_random_uuid()   AS id,
    raw_id,
    inn_name,
    inn_latin,
    inn_list_number,
    inn_year,
    cas_number,
    molecular_formula,
    smiles,
    inchi_key,
    inn_stem,
    stem_definition,
    research_codes,
    synonyms,
    status,
    FALSE               AS processed_to_silver,
    request_timestamp,
    request_timestamp   AS ingested_at,
    'who_inn'           AS source,
    source_updated_at

FROM combined
ORDER BY inn_name, source_updated_at DESC NULLS LAST
