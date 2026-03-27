-- SQLMesh Model: Bronze DrugBank
-- Transforms Raw DrugBank flat-column records to Bronze typed columns
-- Part of: 012-dk-data-platform
--
-- NOTE: raw.drugbank uses flat columns (not response_body JSONB) because
-- DrugBank is a credential-gated XML download parsed by DrugBankFetcher.
-- The loader (sources/drugbank.py) inserts directly into flat columns:
--   drugbank_id, name, description, cas_number, categories (TEXT[]),
--   targets (JSONB), enzymes (JSONB), indication, pharmacodynamics,
--   _source_file, _source_hash, _loaded_at.
-- There is no response_status / processed_to_bronze / request_timestamp
-- on this table — use _loaded_at for time-range incremental partitioning.

MODEL (
    name bronze.drugbank,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column loaded_at,
        batch_size 200
    ),
    cron '@monthly',
    audits (
        not_null(columns := (drugbank_id)),
        unique_values(columns := (drugbank_id))
    ),
    grain drugbank_id
);

SELECT
    gen_random_uuid() AS id,

    -- DrugBank Identifiers
    drugbank_id::TEXT                       AS drugbank_id,
    cas_number::TEXT                        AS cas_number,

    -- Names
    name::TEXT                              AS name,

    -- Drug Properties
    description::TEXT                       AS description,
    indication::TEXT                        AS indication,
    pharmacodynamics::TEXT                  AS pharmacodynamics,

    -- Structured arrays / JSONB from XML parser
    -- categories: TEXT[] from raw — cast to JSONB array for downstream uniformity
    CASE
        WHEN categories IS NOT NULL
        THEN to_jsonb(categories)
        ELSE '[]'::JSONB
    END                                     AS categories,

    -- targets / enzymes: already JSONB from loader
    COALESCE(targets, '[]'::JSONB)          AS targets,
    COALESCE(enzymes, '[]'::JSONB)          AS enzymes,

    -- Fields NOT available from the DrugBank XML fetcher
    -- (these would require a different API endpoint or extended parsing)
    NULL::TEXT                              AS unii,
    NULL::TEXT                              AS drug_type,
    NULL::TEXT                              AS state,
    NULL::JSONB                             AS groups,
    NULL::TEXT                              AS smiles,
    NULL::TEXT                              AS inchi,
    NULL::TEXT                              AS inchi_key,
    NULL::TEXT                              AS molecular_formula,
    NULL::NUMERIC                           AS average_mass,
    NULL::NUMERIC                           AS monoisotopic_mass,
    NULL::JSONB                             AS classification,
    NULL::JSONB                             AS atc_codes,
    NULL::TEXT                              AS mechanism_of_action,
    NULL::TEXT                              AS absorption,
    NULL::TEXT                              AS protein_binding,
    NULL::TEXT                              AS metabolism,
    NULL::TEXT                              AS half_life,
    NULL::TEXT                              AS route_of_elimination,
    NULL::TEXT                              AS clearance,
    NULL::TEXT                              AS volume_of_distribution,
    NULL::TEXT                              AS toxicity,
    NULL::JSONB                             AS drug_interactions,
    NULL::JSONB                             AS food_interactions,
    NULL::JSONB                             AS carriers,
    NULL::JSONB                             AS transporters,
    NULL::JSONB                             AS pathways,
    NULL::JSONB                             AS external_links,
    NULL::JSONB                             AS external_identifiers,
    NULL::JSONB                             AS calculated_properties,
    NULL::JSONB                             AS fda_label,
    NULL::JSONB                             AS patents,
    NULL::JSONB                             AS synonyms,
    NULL::JSONB                             AS international_brands,
    NULL::JSONB                             AS products,

    -- Raw source tracking
    NULL::JSONB                             AS raw_json,
    NULL::UUID                              AS raw_source_id,
    'drugbank'                              AS source,
    _loaded_at                              AS loaded_at,
    _loaded_at                              AS source_updated_at,
    FALSE                                   AS processed_to_silver,
    NOW()                                   AS created_at

FROM raw.drugbank
WHERE
    drugbank_id IS NOT NULL
    AND _loaded_at BETWEEN @start_dt AND @end_dt;
