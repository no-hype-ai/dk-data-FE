-- SQLMesh Model: Silver TGA Medicine Recalls
-- Filters mol_bronze.tga_sara_recalls to regulatory_type ∈ medicine/biological/OTC
-- and resolves sponsor + drug product.
-- Grain: recall_number

MODEL (
    name mol_silver.tga_medicine_recalls,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key recall_number
    ),
    cron '@daily',
    audits (
        not_null(columns := (recall_number))
    ),
    grain recall_number
);

SELECT
    -- Entity-resolved FKs
    mol_silver.resolve_company(
        p_name => b.sponsor_name
    )                                                                AS company_id,

    mol_silver.resolve_drug_product(
        p_brand_name => COALESCE(b.trade_name, b.product_name)
    )                                                                AS product_id,

    -- Natural key
    b.recall_number,

    -- Classification
    b.regulatory_type,
    b.action_type,
    b.risk_classification,

    -- Product
    b.product_name,
    b.trade_name,
    b.artg_number,
    b.batch_numbers,

    -- Sponsor (retained string)
    b.sponsor_name,
    b.manufacturer_name,

    -- Reason
    b.recall_reason,
    b.summary,
    b.description,

    -- Dates
    b.date_published,
    b.date_initiated,
    b.date_closed,
    b.detail_url,

    -- Raw tracking
    b.raw_source_id,
    b.source                                                         AS source_id,
    b.source_updated_at,
    NOW()                                                            AS silver_loaded_at

FROM mol_bronze.tga_sara_recalls AS b
WHERE b.processed_to_silver = FALSE
  AND b.recall_number IS NOT NULL
  AND b.regulatory_type IN ('Medicine', 'Biological', 'OTC', 'Complementary', 'Prescription');
