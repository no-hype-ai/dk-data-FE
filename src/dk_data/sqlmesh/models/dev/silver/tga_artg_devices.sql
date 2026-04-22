-- SQLMesh Model: Silver TGA ARTG Medical Devices
-- Resolves:
--   sponsor_name → company_id via mol_silver.resolve_company
--   (artg_number, product_name, gmdn_code) → device_id via dev_silver.resolve_device
-- Grain: artg_number

MODEL (
    name dev_silver.tga_artg_devices,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key artg_number
    ),
    cron '@weekly',
    audits (
        not_null(columns := (artg_number))
    ),
    grain artg_number
);

SELECT
    -- Entity-resolved FKs
    -- TGA ARTG numbers are not in the current resolve_device priority tiers
    -- (which are: udi_di > k_number > pma_number > fei_number > name). We fall
    -- back to name resolution on product_name. A future migration should add
    -- an 'artg_number' identifier source to dev_silver.device_identifiers and
    -- extend resolve_device with a p_artg_number parameter.
    dev_silver.resolve_device(
        p_name => b.product_name
    )                                                                AS device_id,

    mol_silver.resolve_company(
        p_name => b.sponsor_name
    )                                                                AS company_id,

    -- Manufacturer (may differ from sponsor for imported devices)
    mol_silver.resolve_company(
        p_name => b.manufacturer_name
    )                                                                AS manufacturer_company_id,

    -- Natural key + identity (string retained for audit)
    b.artg_number,
    b.product_name,
    b.product_type,
    b.product_category,

    b.sponsor_name,
    b.manufacturer_name,

    -- Classification
    b.device_classification,                                         -- 'Class I' / 'IIa' / 'IIb' / 'III' / 'AIMD' / 'IVD'
    b.gmdn_term,
    b.gmdn_code,
    b.intended_purpose,

    -- Regulatory
    b.conformity_assessment,
    b.status,
    b.approval_area,

    -- Dates
    b.registration_date,
    b.commencement_date,
    b.cancellation_date,

    -- Raw tracking
    b.raw_source_id,
    b.source                                                         AS source_id,
    b.source_updated_at,
    NOW()                                                            AS silver_loaded_at

FROM dev_bronze.tga_artg_devices AS b
WHERE b.processed_to_silver = FALSE
  AND b.artg_number IS NOT NULL;
