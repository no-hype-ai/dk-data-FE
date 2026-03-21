-- SQLMesh Model: Bronze DrugBank
-- Transforms Raw DrugBank responses to Bronze typed columns
-- Part of: 012-dk-data-platform

MODEL (
    name mol_bronze.drugbank,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
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
    response_body->>'drugbank_id' AS drugbank_id,
    response_body->>'cas_number' AS cas_number,
    response_body->>'unii' AS unii,

    -- Names
    response_body->>'name' AS name,
    response_body->'synonyms' AS synonyms,
    response_body->'international_brands' AS international_brands,
    response_body->'products' AS products,

    -- Drug Properties
    response_body->>'drug_type' AS drug_type,
    response_body->>'state' AS state,
    response_body->'groups' AS groups,
    response_body->>'description' AS description,

    -- Structure
    response_body->>'smiles' AS smiles,
    response_body->>'inchi' AS inchi,
    response_body->>'inchikey' AS inchi_key,
    response_body->>'molecular_formula' AS molecular_formula,
    (response_body->>'average_mass')::NUMERIC AS average_mass,
    (response_body->>'monoisotopic_mass')::NUMERIC AS monoisotopic_mass,

    -- Classification
    response_body->'classification' AS classification,
    response_body->'categories' AS categories,
    response_body->'atc_codes' AS atc_codes,
    response_body->>'indication' AS indication,
    response_body->>'pharmacodynamics' AS pharmacodynamics,
    response_body->>'mechanism_of_action' AS mechanism_of_action,
    response_body->>'absorption' AS absorption,
    response_body->>'protein_binding' AS protein_binding,
    response_body->>'metabolism' AS metabolism,
    response_body->>'half_life' AS half_life,
    response_body->>'route_of_elimination' AS route_of_elimination,
    response_body->>'clearance' AS clearance,
    response_body->>'volume_of_distribution' AS volume_of_distribution,
    response_body->>'toxicity' AS toxicity,

    -- Interactions
    response_body->'drug_interactions' AS drug_interactions,
    response_body->'food_interactions' AS food_interactions,

    -- Targets and Pathways
    response_body->'targets' AS targets,
    response_body->'enzymes' AS enzymes,
    response_body->'carriers' AS carriers,
    response_body->'transporters' AS transporters,
    response_body->'pathways' AS pathways,

    -- External Links
    response_body->'external_links' AS external_links,
    response_body->'external_identifiers' AS external_identifiers,

    -- Calculated Properties
    response_body->'calculated_properties' AS calculated_properties,

    -- Regulatory
    response_body->'fda_label' AS fda_label,
    response_body->'patents' AS patents,

    -- Raw source tracking
    response_body AS raw_json,
    id AS raw_source_id,
    'drugbank' AS source,
    request_timestamp,
    request_timestamp AS source_updated_at,
    FALSE AS processed_to_silver,
    NOW() AS created_at

FROM mol_raw.drugbank
WHERE
    response_status = 200
    AND processed_to_bronze = FALSE
    AND response_body->>'drugbank_id' IS NOT NULL
    AND request_timestamp BETWEEN @start_dt AND @end_dt;
