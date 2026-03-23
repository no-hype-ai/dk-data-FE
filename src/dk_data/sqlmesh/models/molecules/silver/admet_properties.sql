-- SQLMesh Model: Silver ADMET Properties
-- Promotes mol_bronze.tdc_admet into mol_silver.admet_properties with molecule_id linkage.
-- Entity linking: inchi_key (from TDC ADMET data) → mol_silver.molecules.
-- ADMET = Absorption, Distribution, Metabolism, Excretion, Toxicity predictions.

MODEL (
    name mol_silver.admet_properties,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (compound_id, dataset_name))
    )
);

SELECT
    gen_random_uuid()           AS id,
    m.molecule_id,
    b.compound_id,
    b.smiles,
    b.inchi_key,
    b.dataset_name,
    b.dataset_type,
    b.property_name,
    b.property_value,
    b.property_category,
    'tdc_admet'                 AS source,
    b.source_updated_at,
    NOW()                       AS created_at

FROM mol_bronze.tdc_admet b
-- Link via inchi_key
LEFT JOIN mol_silver.molecules m
       ON b.inchi_key IS NOT NULL AND m.inchi_key = b.inchi_key
WHERE b.compound_id IS NOT NULL
  AND b.dataset_name IS NOT NULL;
