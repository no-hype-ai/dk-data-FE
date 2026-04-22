-- SQLMesh Model: Silver TGA Medicine Shortages
-- Resolves sponsor, active ingredient → molecule, and product (via brand_name
-- when resolvable).
-- Grain: shortage_id

MODEL (
    name mol_silver.tga_medicine_shortages,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key shortage_id
    ),
    cron '@daily',
    audits (
        not_null(columns := (shortage_id))
    ),
    grain shortage_id
);

SELECT
    -- Entity-resolved FKs
    mol_silver.resolve_company(
        p_name => b.sponsor_name
    )                                                                AS company_id,

    mol_silver.resolve_molecule(
        p_name => b.active_ingredient
    )                                                                AS molecule_id,

    mol_silver.resolve_drug_product(
        p_brand_name => COALESCE(b.brand_name, b.product_name)
    )                                                                AS product_id,

    -- Natural key + identity
    b.shortage_id,
    b.product_name,
    b.brand_name,
    b.active_ingredient,
    b.artg_number,
    b.schedule,
    b.sponsor_name,

    -- Shortage detail
    b.shortage_status,
    b.shortage_type,
    b.impact,
    b.reason,
    b.management_strategy,

    -- Dates
    b.date_reported,
    b.expected_resolution_date,
    b.date_resolved,

    -- Raw tracking
    b.raw_source_id,
    b.source                                                         AS source_id,
    b.source_updated_at,
    NOW()                                                            AS silver_loaded_at

FROM mol_bronze.tga_medicine_shortages AS b
WHERE b.processed_to_silver = FALSE
  AND b.shortage_id IS NOT NULL;
