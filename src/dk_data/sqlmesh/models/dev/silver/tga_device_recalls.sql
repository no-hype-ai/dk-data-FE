-- SQLMesh Model: Silver TGA Device Recalls
-- Filters mol_bronze.tga_sara_recalls to regulatory_type ∈ device categories.
-- Cross-domain read: bronze lives in mol_bronze but silver lands in dev_silver
-- because the recall concerns a device entity.
-- Grain: recall_number

MODEL (
    name dev_silver.tga_device_recalls,
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
    dev_silver.resolve_device(
        p_name => COALESCE(b.trade_name, b.product_name)
    )                                                                AS device_id,

    mol_silver.resolve_company(
        p_name => b.sponsor_name
    )                                                                AS company_id,

    mol_silver.resolve_company(
        p_name => b.manufacturer_name
    )                                                                AS manufacturer_company_id,

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

    -- Strings
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
  AND b.regulatory_type IN ('Medical device', 'Device', 'IVD', 'AIMD');
