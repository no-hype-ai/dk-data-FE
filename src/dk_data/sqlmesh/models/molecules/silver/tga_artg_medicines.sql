-- SQLMesh Model: Silver TGA ARTG Medicines
-- Entity-resolved ARTG medicines (prescription/OTC/biological/complementary).
-- Resolves:
--   sponsor_name      → company_id via mol_silver.resolve_company (named param p_name)
--   active_ingredients → molecule_id via mol_silver.resolve_molecule (first-ingredient-only fast path)
--   (artg_number, product_name) → product_id via mol_silver.resolve_drug_product
-- Grain: (artg_number, medicine_type)

MODEL (
    name mol_silver.tga_artg_medicines,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (artg_number, medicine_type)
    ),
    cron '@weekly',
    audits (
        not_null(columns := (artg_number, medicine_type))
    ),
    grain (artg_number, medicine_type)
);

SELECT
    -- Entity-resolved FKs (all bigint; named-param calls per add-datasource skill)
    mol_silver.resolve_company(
        p_name => b.sponsor_name
    )                                                                AS company_id,

    -- Resolve molecule from the first active ingredient (ARTG uses pipe-delimited lists;
    -- first element is dominant active ingredient in most cases). Future improvement:
    -- explode into a molecule_artg bridge table.
    mol_silver.resolve_molecule(
        p_name => split_part(b.active_ingredients, '|', 1)
    )                                                                AS molecule_id,

    mol_silver.resolve_drug_product(
        p_brand_name => b.product_name
    )                                                                AS product_id,

    -- Natural keys + classification
    b.artg_number,
    b.medicine_type,                                                 -- prescription | otc | biological | complementary
    b.product_name,
    b.product_type,
    b.product_category,

    -- Retain strings for audit/fallback
    b.sponsor_name,
    b.active_ingredients,

    -- Dosage / form
    b.dosage_form,
    b.route_of_administration,
    b.strength,
    b.strength_unit,
    b.container,
    b.pack_size,

    -- Regulatory
    b.schedule,
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

FROM mol_bronze.tga_artg_medicines AS b
WHERE b.processed_to_silver = FALSE
  AND b.artg_number IS NOT NULL;
