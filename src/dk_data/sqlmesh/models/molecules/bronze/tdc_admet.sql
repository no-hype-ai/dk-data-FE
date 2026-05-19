-- SQLMesh Model: Bronze TDC ADMET
-- Transforms raw Therapeutics Data Commons ADMET predictions into typed bronze layer.
-- Response: {"data": [{Drug_ID, Drug (SMILES), Y (value), InChIKey}]} or
--           {"records": [{compound_id, smiles, value, inchi_key}]}
-- dataset_name is inferred from the request_id suffix (e.g. tdc_admet_BBB → BBB).
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.tdc_admet,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (compound_id, dataset_name)
    ),
    cron '@monthly',
    grain (compound_id, dataset_name),
    audits (
        not_null(columns := (compound_id, dataset_name))
    )
);

WITH unnested_direct AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        COALESCE(
            r.request_params->>'dataset',
            r.request_params->>'dataset_name',
            'unknown'
        ) AS dataset_name,
        rec,
        rec AS raw_json
    FROM mol_raw.tdc_admet r,
         jsonb_array_elements(
             COALESCE(
                 r.response_body->'data',
                 r.response_body->'records',
                 jsonb_build_array(r.response_body)
             )
         ) AS rec
    WHERE r.response_status = 200
      AND r.response_body IS NOT NULL
      AND r.processed_to_bronze = FALSE
)

SELECT
    gen_random_uuid() AS id,
    raw_id,
    COALESCE(
        rec->>'Drug_ID',
        rec->>'compound_id',
        LEFT(rec->>'Drug', 50),
        LEFT(rec->>'smiles', 50)
    ) AS compound_id,
    COALESCE(rec->>'Drug', rec->>'smiles', rec->>'SMILES') AS smiles,
    COALESCE(rec->>'InChIKey', rec->>'inchi_key')           AS inchi_key,
    dataset_name,
    -- Categorise dataset into ADMET tier
    CASE
        WHEN dataset_name ILIKE ANY(ARRAY['%Caco2%','%HIA%','%Pgp%','%Bioavailability%','%Solubility%'])
            THEN 'absorption'
        WHEN dataset_name ILIKE ANY(ARRAY['%Lipophilicity%','%BBB%','%PPBR%','%VDss%'])
            THEN 'distribution'
        WHEN dataset_name ILIKE ANY(ARRAY['%CYP%','%Half_Life%'])
            THEN 'metabolism'
        WHEN dataset_name ILIKE '%Clearance%'
            THEN 'excretion'
        WHEN dataset_name ILIKE ANY(ARRAY['%hERG%','%AMES%','%DILI%','%LD50%','%Carcinogen%','%ClinTox%','%Tox%'])
            THEN 'toxicity'
        ELSE 'other'
    END AS dataset_type,
    (COALESCE(rec->>'Y', rec->>'value', rec->>'label'))::NUMERIC AS property_value,
    CASE
        WHEN dataset_name ILIKE ANY(ARRAY['%Caco2%','%HIA%','%Pgp%','%Bioavailability%','%Solubility%'])
            THEN 'absorption'
        WHEN dataset_name ILIKE ANY(ARRAY['%Lipophilicity%','%BBB%','%PPBR%','%VDss%'])
            THEN 'distribution'
        WHEN dataset_name ILIKE ANY(ARRAY['%CYP%','%Half_Life%'])
            THEN 'metabolism'
        WHEN dataset_name ILIKE '%Clearance%'
            THEN 'excretion'
        WHEN dataset_name ILIKE ANY(ARRAY['%hERG%','%AMES%','%DILI%','%LD50%','%Carcinogen%','%ClinTox%','%Tox%'])
            THEN 'toxicity'
        ELSE 'other'
    END AS property_category,
    raw_json,
    FALSE               AS processed_to_silver,
    request_timestamp,
    request_timestamp   AS ingested_at,
    'tdc_admet'         AS source,
    request_timestamp   AS source_updated_at

FROM unnested_direct
WHERE COALESCE(
    rec->>'Drug_ID',
    rec->>'compound_id',
    rec->>'Drug',
    rec->>'smiles'
) IS NOT NULL
