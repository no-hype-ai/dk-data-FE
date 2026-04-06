-- SQLMesh Model: Silver Orange Book (FDA approved drug products)
-- Promotes mol_bronze.orange_book to silver, linking to mol_silver.molecules.
-- Feature: 019-cms-puf-platform-reconciliation
--
-- Grain: (application_number, product_number, _file_type)
-- Source: mol_bronze.orange_book (from mol_raw.orange_book via OrangeBookFetcher)
-- Covers products, patents, and exclusivity records (distinguished by _file_type).

MODEL (
    name mol_silver.orange_book,
    kind FULL,
    cron '@monthly',
    audits (
        not_null(columns := (application_number))
    ),
    grain (application_number, product_number)
);

SELECT
    b.application_number,
    b.product_number,
    b.ingredient                        AS active_ingredient,
    b.trade_name,
    b.applicant,
    b.applicant                         AS applicant_full_name,
    b.strength,
    b.df_route,
    b.approval_date,
    b.te_code,
    b.rld,
    b.rs,
    b.drug_type                         AS product_type,

    -- Patent info
    b.patent_number,
    b.patent_expiration,
    b.drug_substance_patent,
    b.drug_product_patent,
    b.patent_use_code,

    -- Exclusivity info
    b.exclusivity_code,
    b.exclusivity_date,

    'products'::TEXT                    AS _file_type,
    m.molecule_id,
    b.source,
    b.source_updated_at,
    b.ingested_at                       AS _ingested_at,
    CURRENT_TIMESTAMP                   AS _silver_updated_at
FROM mol_bronze.orange_book AS b
LEFT JOIN mol_silver.molecules AS m
    ON LOWER(TRIM(b.ingredient)) = LOWER(TRIM(m.canonical_name))
WHERE b.application_number IS NOT NULL
