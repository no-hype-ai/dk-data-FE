-- SQLMesh Model: Bronze TDC ADMET
-- Transforms raw Therapeutics Data Commons ADMET predictions into typed bronze layer.
-- Response: {"data": [{Drug_ID, Drug (SMILES), Y (value), InChIKey}]} or
--           {"records": [{compound_id, smiles, value, inchi_key}]}
-- dataset_name is inferred from the request_id suffix (e.g. tdc_admet_BBB → BBB).
-- Part of DK Molecule Data Platform (012-dk-data-platform)

MODEL (
    name mol_bronze.tdc_admet,
    kind INCREMENTAL_BY_TIME_RANGE (
        time_column request_timestamp,
        batch_size 1000
    ),
    cron '@monthly',
    audits (
        not_null(columns := (compound_id, dataset_name, property_name))
    )
);

WITH raw_records AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        -- Dataset name from request params or response
        COALESCE(
            r.request_params->>'dataset',
            r.request_params->>'dataset_name',
            'unknown'
        ) AS dataset_name
    FROM mol_raw.tdc_admet r
    WHERE r.response_status = 200
      AND r.response_body IS NOT NULL
),

-- Unnest data array (TDC returns array of records)
unnested AS (
    SELECT
        rr.raw_id,
        rr.request_timestamp,
        rr.dataset_name,
        rec
    FROM raw_records rr,
         jsonb_array_elements(
             COALESCE(
                 rr.request_timestamp::TEXT::JSONB,  -- never used, just for type
                 (SELECT r2.response_body
                  FROM mol_raw.tdc_admet r2
                  WHERE r2.id = rr.raw_id)->'data',
                 (SELECT r2.response_body
                  FROM mol_raw.tdc_admet r2
                  WHERE r2.id = rr.raw_id)->'records',
                 '[]'::JSONB
             )
         ) AS rec
),

-- Simpler: unnest directly from the source table
unnested_direct AS (
    SELECT
        r.id AS raw_id,
        r.request_timestamp,
        COALESCE(
            r.request_params->>'dataset',
            r.request_params->>'dataset_name',
            'unknown'
        ) AS dataset_name,
        rec
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
    dataset_name AS property_name,
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
